import collections
import logging
from datetime import datetime, time, timedelta

from ogn_lib import exceptions


FEET_TO_METERS = 0.3048
KNOTS_TO_MS = 1852 / 3600  # ratio between nautical knots and m/s

TD_1DAY = timedelta(days=1)


logger = logging.getLogger(__name__)


class ParserBase(type):
    """
    Metaclass for all parsers.
    """

    parsers = {}

    def __new__(meta, name, bases, dct):
        """
        Creates a new ParserBase class.

        Class callsigns are registered using the `__destto__` field of every
        class. If `__destto__` is not set, class name is used instead.
        """

        class_ = super().__new__(meta, name, bases, dct)
        callsigns = dct.get('__destto__', name)

        if isinstance(callsigns, str):
            logger.debug('Setting %s as a parser for %s messages', name, callsigns)
            meta.parsers[callsigns] = class_
        elif isinstance(callsigns, collections.Sequence):
            for c in callsigns:
                logger.debug('Setting %s as a parser for %s messages', name, c)
                meta.parsers[c] = class_
        else:
            raise TypeError('instance of __destto__ should be either a sequence'
                            'or a string; is {}'.format(type(callsigns)))

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

        _, body = raw_message.split('>', 1)
        destto, *_ = body.split(',', 1)

        try:
            parser = cls.parsers[destto]
            logger.debug('Using %s parser for %s', parser, raw_message)
        except KeyError:
            raise exceptions.ParserNotFoundError(
                'Parser for a destto name {} not found; found: {}'
                .format(destto, list(cls.parsers.keys())))

        return parser.parse_message(raw_message)


class Parser(metaclass=ParserBase):
    """
    Base class for all parser classes.

    Implements parsing of APRS message header and calls the populates the data
    with the values returned by the _parse_comment(comment) of the extending
    class.
    """

    @staticmethod
    def parse_message(raw_message):
        """
        Parses the fields of a raw APRS message to a dictionary.

        :param str raw_message: raw APRS message
        :return: parsed message
        :rtype: dict
        """

        from_, body = raw_message.split('>', 1)
        header, *comment = body.split(' ', 1)

        data = {'from': from_}
        data.update(Parser._parse_header(header))

        if comment:
            data.update(Parser.parse_comment(comment))

        return data

    @staticmethod
    def _parse_header(header):
        """
        Parses the APRS message header.

        :param str header: APRS message between the '[callsign]>' and comment
                           field
        :return: parsed header
        :rtype: dict
        """

        origin, position = header.split(':/', 1)

        data = Parser._parse_origin(origin)
        data.update(Parser._parse_position(position))

        return data

    @staticmethod
    def _parse_origin(header):
        """
        Parses the destto, receiver and relayer field of the APRS message.
        :param str header: APRS message between the '[callsign]>' and position
                           information
        :return: parsed origin part of the APRS message
        :rtype: dict
        """

        fields = header.split(',')

        if len(fields) == 3:  # standard message
            relayer = None
        elif len(fields) == 4:  # relayed message
            relayer = fields[2].strip('*')
        else:
            raise ValueError('Unknown header format: {}'.format(header))

        data = {'destto': fields[0], 'receiver': fields[-1], 'relayer': relayer}

        return data

    @staticmethod
    def _parse_position(pos_header):
        """
        Parses the position information, timestamp, altitude, heading and
        ground speed from an APRS message.

        :param str pos_header: position part of the APRS header
        :return: parsed position part of the APRS message
        :rtype: dict
        """

        timestamp = pos_header[0:6]
        position, attrs = pos_header[7:].split('\'', 1)
        lat, lon = position.split('/')
        heading, speed, altitude = map(lambda x: int(x),
                                       attrs.replace('A=', '').split('/'))

        data = {
            'timestamp': Parser._parse_timestamp(timestamp),
            'latitude': Parser._parse_location(lat),
            'longitude': Parser._parse_location(lon),
            'altitude': altitude * FEET_TO_METERS
        }

        if heading or speed:
            data['heading'] = heading
            data['ground_speed'] = speed * KNOTS_TO_MS
        else:
            data['heading'] = None
            data['ground_speed'] = None

        return data

    @staticmethod
    def _parse_timestamp(timestamp_str):
        """
        Parses the UTC timestamp of an APRS package.

        :param timestamp_str: utc timestamp string in %H%M%S format
        :return: parsed timestamp
        :rtype: datetime.datetime
        """

        ts = time(*map(lambda x: int(x),
                       map(lambda x: timestamp_str[x * 2: x * 2 + 2], range(3))))
        full_ts = datetime.combine(datetime.utcnow(), ts)

        now = datetime.utcnow()
        print(now, full_ts)

        td = (now - full_ts).total_seconds()
        if td < -300:
            full_ts -= TD_1DAY

        return full_ts

    @staticmethod
    def _parse_location(location_str):
        """
        Parses the location string and returns a signed decimal position.

        :param location_str: location string in the standard APRS format
        :return: signed decimal latitude/longitude
        :rtype: float
        """

        sphere = location_str[-1]
        offset = 2 if sphere in ('N', 'S') else 3

        location = int(location_str[:offset])
        location += float(location_str[offset:offset + 5]) / 60

        if sphere in ('S', 'W'):
            location *= -1

        return location


class APRS(Parser):
    """
    Parser for the orignal OGN-flavoured APRS messages.
    """

    __destto__ = 'APRS'

    @staticmethod
    def _parse_comment(comment):
        return {}


class Naviter(Parser):
    """
    Parser for the Naviter-formatted APRS messages.
    """

    __destto__ = ['OGNAVI', 'OGNAVI-1']

    @staticmethod
    def _parse_comment(comment):
        return {}
