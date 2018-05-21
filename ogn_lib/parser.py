import collections
import functools
import logging
import re
from datetime import datetime, time, timedelta

from ogn_lib import constants, exceptions


FEET_TO_METERS = 0.3048
KNOTS_TO_MS = 1852 / 3600  # ratio between nautical knots and m/s
HPM_TO_DEGS = 180 / 60  # ratio between half turn per minute and degrees per s
FPM_TO_MS = FEET_TO_METERS / 60

TD_1DAY = timedelta(days=1)


logger = logging.getLogger(__name__)


class ParserBase(type):
    """
    Metaclass for all parsers.
    """

    parsers = {}
    default = None

    def __new__(meta, name, bases, dct):
        """
        Creates a new ParserBase class.

        Class callsigns are registered using the `__destto__` field of every
        class. If `__destto__` is not set, class name is used instead.
        """

        class_ = super().__new__(meta, name, bases, dct)
        callsigns = dct.get('__destto__', name)
        default = dct.get('__default__', False)

        if isinstance(callsigns, str):
            logger.debug('Setting %s as a parser for %s messages', name, callsigns)
            meta.parsers[callsigns] = class_
        elif isinstance(callsigns, collections.Sequence):
            for c in callsigns:
                logger.debug('Setting %s as a parser for %s messages', name, c)
                meta.parsers[c] = class_
        elif callsigns is None:
            pass
        else:
            raise TypeError('instance of __destto__ should be either a sequence'
                            'or a string; is {}'.format(type(callsigns)))

        if default:
            meta.default = class_

        return class_

    @classmethod
    def __call__(cls, raw_message):
        """
        Parses the fields of a raw APRS message to a dictionary by calling the
        underlying method ParserBase._parse_message.

        :param str raw_message: raw APRS message
        :return: parsed message
        :rtype: dict
        :raises ogn_lib.exceptions.ParserNotFoundError: if parser for this
            message's callsign was not found
        """

        try:
            _, body = raw_message.split('>', 1)
            destto, *_ = body.split(',', 1)

            if 'TCPIP*' in body:
                return ServerParser.parse_message(raw_message)

            try:
                parser = cls.parsers[destto]
                logger.debug('Using %s parser for %s', parser, raw_message)
            except KeyError:
                logger.warn('Parser for a destto name %s not found; found: %s',
                            destto, list(cls.parsers.keys()))

                if cls.default:
                    parser = cls.default
                else:
                    raise exceptions.ParserNotFoundError(
                        'Parser for a destto name {} not found; found: {}'
                        .format(destto, list(cls.parsers.keys())))

            return parser.parse_message(raw_message)

        except exceptions.ParserNotFoundError:
            raise
        except Exception as e:
            msg = 'Failed to parse message: {}'.format(raw_message)
            logger.error(msg)
            logger.exception(e)
            raise exceptions.ParseError(msg)


class Parser(metaclass=ParserBase):
    """
    Base class for all parser classes.

    Implements parsing of APRS message header and calls the populates the data
    with the values returned by the _parse_protocol_specific(comment) of the
    extending class.
    """

    __default__ = True

    # TNC-2 formatted header (p. 84)
    PATTERN_HEADER = re.compile('(?P<source>.{1,9})'
                                '>(?P<destination>.{1,9}?)'
                                '(,(?P<digipeaters>.{0,80}))'
                                ':(?P<data>.*?)$')

    # Lat/Long Position Report Format - with Timestamp (p. 32)
    PATTERN_LOCATION = re.compile('(@|/)'
                                  '(?P<time>\d{6}(z|h))'
                                  '(?P<latitude>\d{4}\.\d{2}(N|S))'
                                  '(/|\\\\|I)(?P<longitude>\d{5}\.\d{2}(E|W))')

    PATTERN_COMMENT_COMON = re.compile('((?P<heading>\d{3})/(?P<speed>\d{3}))?'
                                       '(/A=(?P<altitude>\d{6}))?'
                                       '( (?P<protocol_specific>.*?))?$')

    # Merged header and position
    PATTERN_ALL = re.compile('(?P<source>.{1,9})>'
                             '(?P<destination>.{1,9}?)'
                             '(,(?P<digipeaters>.{0,81})):'
                             '(@|/)'
                             '(?P<time>\d{6}(z|h))'
                             '(?P<latitude>\d{4}\.\d{2}(N|S))'
                             '.(?P<longitude>\d{5}\.\d{2}(E|W))'
                             '.((?P<heading>\d{3})/(?P<speed>\d{3}))?'
                             '(/A=(?P<altitude>\d{6}))?'
                             '( (?P<protocol_specific>.*?))?$')

    @classmethod
    def parse_message(cls, raw_message):
        """
        Parses the fields of a raw APRS message to a dictionary. Returns
        none if message could not be parsed.

        :param str raw_message: raw APRS message
        :return: parsed message or None if the message failed to parse
        :rtype: dict or None
        :raises ogn_lib.exceptions.ParseError: if message cannot be parsed
            using Parser.PATTERN_ALL
        """

        raw_message = cls._preprocess_message(raw_message)

        match = cls.PATTERN_ALL.match(raw_message)

        if not match:
            raise exceptions.ParseError('Message {} did not match {}'
                                        .format(raw_message, cls.PATTERN_ALL))

        data = {
            'from': match.group('source'),
            'destto': match.group('destination'),
            'beacon_type': constants.BeaconType.aircraft_beacon,
            'timestamp': Parser._parse_timestamp(match.group('time')),
            'latitude': Parser._parse_location(match.group('latitude')),
            'longitude': Parser._parse_location(match.group('longitude')),
            'altitude': Parser._parse_altitude(match.group('altitude'))
        }
        data.update(Parser._parse_digipeaters(match.group('digipeaters')))
        data.update(Parser._parse_heading_speed(match.group('heading'),
                                                match.group('speed')))

        protocol_specific = match.group('protocol_specific')
        if protocol_specific:
            comment_data = cls._parse_protocol_specific(protocol_specific)

            try:
                cls._update_data(data, comment_data['_update'])
                del comment_data['_update']
            except KeyError:
                logger.debug('comment_data[\'_update\'] not set')

            data.update(comment_data)

        data['raw'] = raw_message
        return data

    @staticmethod
    def _preprocess_message(message):
        """
        Performs additional preprocessing on the received APRS message.

        :param str message: the received message
        :return: processed message
        :rtype: str
        """

        return message

    @staticmethod
    def _parse_digipeaters(digipeaters):
        """
        Parses the content of the APRS digipeaters field and extracts the
        information about the receiver and the relayer.

        :param str digipeaters: digipeaters string from the original message
        :return: dictionary with the receiver and the relayer
        :rtype: dict
        :raises ValueError: if digipeaters string is in invalid format
        """

        fields = digipeaters.split(',')

        if len(fields) == 2:  # standard message
            relayer = None
        elif len(fields) == 3:  # relayed message
            relayer = fields[0].strip('*')
        else:
            raise ValueError('Unknown digipeaters format: {}'
                             .format(digipeaters))

        return {'receiver': fields[-1], 'relayer': relayer}

    @staticmethod
    def _parse_heading_speed(heading, speed):
        """
        Parses and converts the heading and speed from the original message
        to the appropriate units.

        :param str heading: heading string
        :param str speed: speed string
        :return: dictionary containing the heading and ground speed in m/s
        :rtype: dict
        """

        if not heading or not speed:
            return {}

        hdg = int(heading)
        gsp = int(speed)

        data = {}

        if hdg or gsp:
            data['heading'] = hdg
            data['ground_speed'] = gsp * KNOTS_TO_MS
        else:
            data['heading'] = None
            data['ground_speed'] = None

        return data

    @staticmethod
    def _parse_altitude(altitude_string):
        """
        Parses the altitude string and converts it from feet to meters.

        :param altitude_string: the altitude string
        :type altitude_string: str or None
        :return: altitude in meters or None if altitude_str is not given
        :rtype: float or None
        """

        return int(altitude_string) * FEET_TO_METERS if altitude_string else None

    @staticmethod
    def _parse_timestamp(timestamp_str):
        """
        Parses the timestamp of an APRS package.

        :param str timestamp_str: timestamp string in %H%M%S or %d%H%M format
        :return: parsed timestamp
        :rtype: datetime.datetime
        """

        ts_str = timestamp_str[:6]
        type_ = timestamp_str[-1]

        if type_ == 'h':
            return Parser._parse_time(ts_str)
        else:
            return Parser._parse_datetime(ts_str)

    @staticmethod
    def _parse_time(timestamp):
        """
        Parses the HMS formated timestamp string.

        :param timestamp_str: utc timestamp string in %H%M%S
        :return: parsed timestamp
        :rtype: datetime.datetime
        """

        ts = time(*map(lambda x: int(x),
                       map(lambda x: timestamp[x * 2: x * 2 + 2], range(3))))
        full_ts = datetime.combine(datetime.utcnow(), ts)

        now = datetime.utcnow()

        td = (now - full_ts).total_seconds()
        if td < -300:
            full_ts -= TD_1DAY

        return full_ts

    @staticmethod
    def _parse_datetime(timestamp):
        """
        Parses the HMS formated timestamp string.

        :param timestamp_str: utc timestamp string in %H%M%S
        :return: parsed timestamp
        :rtype: datetime.datetime
        """

        ts = list(map(lambda x: int(x),
                      map(lambda x: timestamp[x * 2: x * 2 + 2], range(3))))

        now = datetime.now()
        date_ = datetime(now.year, now.month, ts[0])
        time_ = time(ts[1], ts[2], 0)

        full_ts = datetime.combine(date_, time_)

        return full_ts

    @staticmethod
    def _parse_location(location_str):
        """
        Parses the location string and returns a signed decimal position.

        :param location_str: location string in the standard APRS format
        :return: signed decimal latitude/longitude
        :rtype: float
        """

        if not location_str:
            return None

        sphere = location_str[-1]
        offset = 2 if sphere in ('N', 'S') else 3

        location = int(location_str[:offset])
        location += float(location_str[offset:offset + 5]) / 60

        if sphere in ('S', 'W'):
            location *= -1

        return location

    @staticmethod
    def _parse_protocol_specific(comment):
        """
        Parses the comment string from APRS messages.

        :param str comment: comment string
        :return: parsed comment
        :rtype: dict
        """

        logger.warn('Parser._parse_protocol_specific method not overriden')
        return {}

    @staticmethod
    def _convert_fpm_to_ms(fpm_string):
        """Parses and converts a vertical speed string from '+123fpm' to a
        floating point number in m/s.

        :param str fpm_string: vertical speed string
        :return: vertical speed in m/s
        :rtype: float
        """

        return int(fpm_string[:-3]) * FPM_TO_MS

    @staticmethod
    def _get_location_update_func(update_with):
        """
        Builds a partial function for updating location with 3rd additional
        decimal.

        :param int update_with: 3rd decimal
        :return: partial function updating position with 3rd digit
        :rtype: callable
        """

        return functools.partial(Parser._update_location_decimal,
                                 update=update_with)

    @staticmethod
    def _update_location_decimal(existing, update):
        """
        Updates location with 3rd additional decimal.

        :param float existing: existing value
        :param int update: 3rd decimal
        :return: new location
        :rtype: float
        """

        delta = update
        if existing < 0:
            delta *= -1

        return existing + delta / 60000

    def _update_data(data, updates):
        """
        Updates the existing data with values described in `updates`.

        Updates are a list of dictionaries. Each dictionary should have two
        keys: `target` that contains the key from `data` which should be
        updated, and `function` which describes the update function.

        :param dict data: existing data
        :param list updates: list of updates
        :return: updated data
        :rtype: dict
        """

        for update in updates:
            try:
                key = update['target']
                value = data[key]
                data[key] = update['function'](value)
            except KeyError:
                logger.error('Key for update %s not found', update['target'])

        return data


class APRS(Parser):
    """
    Parser for the orignal OGN-flavoured APRS messages.
    """

    __destto__ = ['APRS', 'OGFLR', 'OGNTRK']

    FLAGS_STEALTH = 1 << 7
    FLAGS_DO_NOT_TRACK = 1 << 6
    FLAGS_AIRCRAFT_TYPE = 0b1111 << 2
    FLAGS_ADDRESS_TYPE = 0b11

    @staticmethod
    def _parse_protocol_specific(comment):
        """
        Parses the comment string from APRS messages.

        :param str comment: comment string
        :return: parsed comment
        :rtype: dict
        """

        data = {}
        fields = comment.split(' ')
        for field in fields:
            if field.startswith('!') and field.endswith('!'):  # 3rd decimal
                lat_dig = int(field[2])
                lon_dig = int(field[3])
                update_position = [
                    {
                        'target': 'latitude',
                        'function': Parser._get_location_update_func(lat_dig)
                    }, {
                        'target': 'longitude',
                        'function': Parser._get_location_update_func(lon_dig)
                    }
                ]
                try:
                    for u in update_position:
                        data['_update'].append(u)
                except KeyError:
                    data['_update'] = update_position
            elif field.startswith('id'):
                data.update(APRS._parse_id_string(field[2:]))
            elif field.endswith('fpm'):  # vertical speed
                data['vertical_speed'] = Parser._convert_fpm_to_ms(field)
            elif field.endswith('rot'):  # turn rate
                data['turn_rate'] = float(field[:-3]) * HPM_TO_DEGS
            elif field.startswith('FL'):  # (optional) flight level
                data['flight_level'] = float(field[2:])
            elif field.endswith('dB'):  # signal to noise ratio
                data['signal_to_noise_ratio'] = float(field[:-2])
            elif field.endswith('e'):  # error count
                data['error_count'] = int(field[:-1])
            elif field.endswith('kHz'):  # frequency offset
                data['frequency_offset'] = float(field[:-3])
            elif field.startswith('gps'):  # (optional) gps quality
                x_idx = field.find('x')
                data['gps_quality'] = {
                    'vertical': int(field[x_idx + 1:]),
                    'horizontal': int(field[3:x_idx])
                }
            elif field.startswith('s'):  # (optional) flarm software version
                data['flarm_software'] = field[1:]
            elif field.startswith('r'):  # (optional) flarm id
                data['flarm_id'] = field[1:]
            elif field.endswith('dBm'):  # (optional) power ratio
                data['power_ratio'] = float(field[:-3])
            elif field.startswith('hear'):  # (optional) other devices heard
                try:
                    data['other_devices'].append(field[4:])
                except KeyError:
                    data['other_devices'] = [field[4:]]
            elif field.startswith('h'):  # (optional) flarm hardware version
                data['flarm_hardware'] = int(field[1:], 16)

        return data

    @staticmethod
    def _parse_id_string(id_string):
        """
        Parses the information encoded in the id string.

        :param str id_string: unique identification string
        :return: parsed information
        :rtype: dict
        """

        flags = int(id_string[:2], 16)
        return {
            'uid': id_string,
            'stealth': bool(flags & APRS.FLAGS_STEALTH),
            'do_not_track': bool(flags & APRS.FLAGS_DO_NOT_TRACK),
            'aircraft_type': constants.AirplaneType(
                (flags & APRS.FLAGS_AIRCRAFT_TYPE) >> 2),
            'address_type': constants.AddressType(flags & APRS.FLAGS_ADDRESS_TYPE)
        }


class Naviter(Parser):
    """
    Parser for the Naviter-formatted APRS messages.
    """

    __destto__ = ['OGNAVI', 'OGNAVI-1']

    FLAGS_STEALTH = 1 << 15
    FLAGS_DO_NOT_TRACK = 1 << 14
    FLAGS_AIRCRAFT_TYPE = 0b1111 << 10
    FLAGS_ADDRESS_TYPE = 0b111111 << 4

    @staticmethod
    def _parse_protocol_specific(comment):
        """
        Parses the comment string from Naviter's APRS messages.

        :param str comment: comment string
        :return: parsed comment
        :rtype: dict
        """

        data = {}
        fields = comment.split(' ')
        for field in fields:
            if field.startswith('!') and field.endswith('!'):  # 3rd decimal
                lat_dig = int(field[2])
                lon_dig = int(field[3])
                update_position = [
                    {
                        'target': 'latitude',
                        'function': Parser._get_location_update_func(lat_dig)
                    }, {
                        'target': 'longitude',
                        'function': Parser._get_location_update_func(lon_dig)
                    }
                ]
                try:
                    for u in update_position:
                        data['_update'].append(u)
                except KeyError:
                    data['_update'] = update_position
            elif field.startswith('id'):
                data.update(Naviter._parse_id_string(field[2:]))
            elif field.endswith('fpm'):  # vertical speed
                data['vertical_speed'] = Parser._convert_fpm_to_ms(field)
            elif field.endswith('rot'):  # turn rate
                data['turn_rate'] = float(field[:-3]) * HPM_TO_DEGS

        return data

    @staticmethod
    def _parse_id_string(id_string):
        """
        Parses the information encoded in the id string.

        :param str id_string: unique identification string
        :return: parsed information
        :rtype: dict
        """

        flags = int(id_string[:4], 16)
        return {
            'uid': id_string,
            'stealth': bool(flags & Naviter.FLAGS_STEALTH),
            'do_not_track': bool(flags & Naviter.FLAGS_DO_NOT_TRACK),
            'aircraft_type': constants.AirplaneType(
                (flags & Naviter.FLAGS_AIRCRAFT_TYPE) >> 10),
            'address_type': constants.AddressType(
                (flags & Naviter.FLAGS_ADDRESS_TYPE) >> 4)
        }


class ServerParser(Parser):
    """
    Parser for server messages.
    """

    __destto__ = None

    PATTERN_ALL = re.compile('(?P<source>.{1,9})>'
                             '(?P<destination>.{1,9}?)'
                             '(,(?P<digipeaters>.{0,81})):'
                             '(@|/|>)'
                             '(?P<time>\d{6}(z|h))'
                             '((?P<latitude>\d{4}\.\d{2}(N|S))'
                             '.(?P<longitude>\d{5}\.\d{2}(E|W)))?'
                             '(.((?P<heading>\d{3})/(?P<speed>\d{3}))?'
                             '(/A=(?P<altitude>\d{6}))?)?'
                             '( (?P<protocol_specific>.*?))?$')

    @classmethod
    def parse_message(cls, raw_message):
        """
        Parses the server message using the Parser.parse_message.

        :param str raw_message: raw APRS message
        :return: parsed message
        :rtype: dict
        """

        data = super().parse_message(raw_message)

        if 'comment' in data:
            data['beacon_type'] = constants.BeaconType.server_status
        else:
            data['beacon_type'] = constants.BeaconType.server_beacon

        return data

    @staticmethod
    def _parse_protocol_specific(comment):
        """
        Converts the comment field from the server status message to a format
        expected by Parser.parse_message

        :param str comment: status comment
        :return: dictionary with the comment
        :rtype: dict
        """

        return {'comment': comment}


class Spot(Parser):
    """
    Parser for Spot-formatted APRS messages.
    """

    __destto__ = ['OGSPOT', 'OGSPOT-1']

    @staticmethod
    def _parse_protocol_specific(comment):
        """
        Parses the comment string from Spot's APRS messages.
        :param str comment: comment string
        :return: parsed comment
        :rtype: dict
        """

        fields = comment.split(' ', maxsplit=2)

        if len(fields) < 3:
            raise exceptions.ParseError('SPOT comment incorrectly formatted: '
                                        'received {}'.format(comment))

        return {
            'id': fields[0],
            'model': fields[1],
            'status': fields[2]
        }


class Spider(Parser):
    """
    Parser for Spider-formatted APRS messages.
    """

    __destto__ = ['OGSPID', 'OGSPID-1']

    @staticmethod
    def _parse_protocol_specific(comment):
        """
        Parses the comment string from Spider's APRS messages.
        :param str comment: comment string
        :return: parsed comment
        :rtype: dict
        """

        fields = comment.split(' ', maxsplit=3)

        if len(fields) < 4:
            raise exceptions.ParseError('Spider comment incorrectly formatted:'
                                        ' received {}'.format(comment))

        return {
            'id': fields[0],
            'signal_strength': fields[1],
            'spider_id': fields[2],
            'gps_status': fields[3]
        }


class Skylines(Parser):
    """
    Parser for Spider-formatted APRS messages.
    """

    __destto__ = ['OGSKYL', 'OGSKYL-1']

    @staticmethod
    def _parse_protocol_specific(comment):
        """
        Parses the comment string from Spider's APRS messages.
        :param str comment: comment string
        :return: parsed comment
        :rtype: dict
        """

        fields = comment.split(' ', maxsplit=1)

        if len(fields) < 2:
            raise exceptions.ParseError('Skylines comment incorrectly formatted:'
                                        ' received {}'.format(comment))

        return {
            'id': fields[0],
            'vertical_speed': Parser._convert_fpm_to_ms(fields[1])
        }


class LiveTrack24(Parser):
    """
    Parser for LiveTrack24-formatted APRS messages.
    """

    __destto__ = ['OGLT24', 'OGLT24-1']

    @staticmethod
    def _parse_protocol_specific(comment):
        """
        Parses the comment string from LiveTrack24's APRS messages.
        :param str comment: comment string
        :return: parsed comment
        :rtype: dict
        """

        fields = comment.split(' ', maxsplit=2)

        if len(fields) < 3:
            raise exceptions.ParseError('LT24 comment incorrectly formatted:'
                                        ' received {}'.format(comment))

        return {
            'id': fields[0],
            'vertical_speed': Parser._convert_fpm_to_ms(fields[1]),
            'source': fields[2]
        }


class Capturs(Parser):
    __destto__ = ['OGCAPT', 'OGCAPT-1']

    @staticmethod
    def _preprocess_message(message):
        return message.strip('/')


class Fanet(Parser):
    """
    Parser for Fanet-formatted APRS messages.
    """

    __destto__ = ['OGNFNT', 'OGNFNT-1']

    @staticmethod
    def _parse_protocol_specific(comment):
        """
        Parses the comment string from Fanet's APRS messages.
        :param str comment: comment string
        :return: parsed comment
        :rtype: dict
        """

        fields = comment.split(' ')

        if len(fields) != 3:
            raise exceptions.ParseError('Fanet comment incorrectly formatted:'
                                        ' received {}'.format(comment))

        lat_dig = int(fields[0][2])
        lon_dig = int(fields[0][3])
        update_position = [
            {
                'target': 'latitude',
                'function': Parser._get_location_update_func(lat_dig)
            }, {
                'target': 'longitude',
                'function': Parser._get_location_update_func(lon_dig)
            }
        ]

        return {
            '_update': update_position,
            'id': fields[1],
            'vertical_speed': Parser._convert_fpm_to_ms(fields[2])
        }
