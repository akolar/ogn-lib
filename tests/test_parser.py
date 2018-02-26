import os
import pytest
from datetime import datetime, timedelta, time
from ogn_lib import exceptions, parser, constants


def get_messages(n_messages=float('inf')):
    test_dir = os.path.dirname(os.path.realpath(__file__))

    with open(os.path.join(test_dir, 'messages.txt'), 'r') as f:
        lines = f.readlines()

    messages = []
    for i, l in enumerate(lines):
        if i >= n_messages:
            break

        messages.append(l.strip())

    return messages


class TestParserBase:

    def test_new_no_id(self):
        class Callsign(parser.Parser):
            pass

        assert 'Callsign' in parser.ParserBase.parsers

    def test_new_single_id(self):
        class Callsign(parser.Parser):
            __destto__ = 'CALL1234'

        assert 'CALL1234' in parser.ParserBase.parsers

    def test_new_multi_id(self):
        class Callsign(parser.Parser):
            __destto__ = ['CALL234', 'CALL4321']

        assert 'CALL234' in parser.ParserBase.parsers
        assert 'CALL4321' in parser.ParserBase.parsers

    def test_no_destto(self):
        old = parser.ParserBase.parsers

        class Anon(parser.Parser):
            __destto__ = None

        assert parser.ParserBase.parsers == old
        assert 'Anon' not in parser.ParserBase.parsers

    def test_new_wrong_id(self):
        with pytest.raises(TypeError):
            class Callsign(parser.Parser):
                __destto__ = 12345678

    def test_set_default(self):
        class Callsign(parser.Parser):
            __default__ = True

        assert parser.ParserBase.default is Callsign

    def test_call(self, mocker):
        class Callsign(parser.Parser):
            __destto__ = 'CALLSIGN'

            parse_message = mocker.Mock()

        msg = ('FLRDD83BC>CALLSIGN,qAS,EDLF:/163148h5124.56N/00634.42E\''
               '276/075/A=001551')
        parser.ParserBase.__call__(msg)

        Callsign.parse_message.assert_called_once_with(msg)

    def test_call_server(self, mocker):
        with mocker.patch('ogn_lib.parser.ServerParser.parse_message'):
            msg = ('LKHS>APRS,TCPIP*,qAC,GLIDERN2:/211635h4902.45NI01429.51E&'
                   '000/000/A=001689')
            parser.ParserBase.__call__(msg)

            parser.ServerParser.parse_message.assert_called_once_with(msg)

    def test_call_no_parser(self):
        with pytest.raises(exceptions.ParserNotFoundError):
            parser.ParserBase.default = None
            parser.ParserBase.__call__(
                'FLRDD83BC>APRS-1,qAS,EDLF:/163148h5124.56N/00634.42E\''
                '276/075/A=001551')

    def test_call_default(self, mocker):
        class Callsign(parser.Parser):
            __default__ = True

            parse_message = mocker.Mock()

        msg = ('FLRDD83BC>Unknown,qAS,EDLF:/163148h5124.56N/00634.42E\''
               '276/075/A=001551')
        parser.ParserBase.__call__(msg)

        Callsign.parse_message.assert_called_once_with(msg)

    def test_call_failed(self, mocker):
        with mocker.patch('ogn_lib.parser.Parser.parse_message',
                          side_effect=ValueError):
            with pytest.raises(exceptions.ParseError):
                parser.ParserBase.__call__('FLR123456>APRS,')


class TestParser:
    messages = get_messages()

    message = ("FLRDDA5BA>APRS,qAS,LFMX:/165829h4415.41N/00600.03E'342/049/A="
               "005524 id0ADDA5BA -454fpm -1.1rot 8.8dB 0e+51.2kHz gps4x5")

    expected_matches = {
        'source': 'FLRDDA5BA',
        'destination': 'APRS',
        'digipeaters': 'qAS,LFMX',
        'time': '165829h',
        'latitude': '4415.41N',
        'longitude': '00600.03E',
        'altitude': '005524',
        'speed': '049',
        'heading': '342'
    }

    def _test_matches_all(self, pattern):
        for msg in self.messages:
            match = pattern.search(msg)
            if not match:
                raise Exception('Message not matched: {}'.format(msg))

    def _test_pattern_field(self, pattern, field):
        match = pattern.search(self.message)
        assert match.group(field) == self.expected_matches[field]

    def test_pattern_header(self):
        for field in ['source', 'destination', 'digipeaters']:
            self._test_pattern_field(parser.Parser.PATTERN_HEADER, field)

        match = parser.Parser.PATTERN_HEADER.match(self.message)
        assert match.group('data')

    def test_pattern_header_matches_all(self):
        self._test_matches_all(parser.Parser.PATTERN_HEADER)

    def test_pattern_location(self):
        for field in ['time', 'latitude', 'longitude']:
            self._test_pattern_field(parser.Parser.PATTERN_LOCATION, field)

    def test_pattern_location_matches_all(self):
        self._test_matches_all(parser.Parser.PATTERN_LOCATION)

    def test_pattern_comment_common(self):
        for field in ['heading', 'speed', 'altitude']:
            self._test_pattern_field(parser.Parser.PATTERN_COMMENT_COMON, field)

    def test_pattern_comment_common_matches_all(self):
        self._test_matches_all(parser.Parser.PATTERN_COMMENT_COMON)

    def test_pattern_all(self):
        for k in self.expected_matches.keys():
            self._test_pattern_field(parser.Parser.PATTERN_ALL, k)

    def test_pattern_all_matches_all(self):
        self._test_matches_all(parser.Parser.PATTERN_ALL)

    def test_parse_msg_no_match(self):
        with pytest.raises(exceptions.ParseError):
            parser.Parser.parse_message('invalid message')

    def test_parse_msg_calls(self, mocker):
        mocker.spy(parser.Parser, '_parse_timestamp')
        mocker.spy(parser.Parser, '_parse_location')
        mocker.spy(parser.Parser, '_parse_altitude')
        mocker.spy(parser.Parser, '_parse_digipeaters')
        mocker.spy(parser.Parser, '_parse_heading_speed')
        mocker.spy(parser.Parser, '_parse_protocol_specific')

        parser.Parser.parse_message(
            'FLRDD83BC>APRS,qAS,EDLF:/163148h5124.56N/00634.42E\''
            '276/075/A=001551')

        parser.Parser._parse_timestamp.assert_called_once_with('163148h')
        assert parser.Parser._parse_location.call_count == 2
        parser.Parser._parse_altitude.assert_called_once_with('001551')
        parser.Parser._parse_digipeaters.assert_called_once_with('qAS,EDLF')
        parser.Parser._parse_heading_speed.assert_called_once_with('276', '075')
        parser.Parser._parse_protocol_specific.assert_not_called()

    def test_parse_msg(self, mocker):
        data = parser.Parser.parse_message(
            'FLRDD83BC>APRS,qAS,EDLF:/163148h5124.56N/00634.42E\''
            '276/075/A=001551')

        assert data['from'] == 'FLRDD83BC'
        assert data['destto'] == 'APRS'

    def test_parse_msg_full(self, mocker):
        msg = ('NAV07220E>OGNAVI,qAS,NAVITER:/125447h4557.77N/01220.19E\'258/'
               '056/A=006562 !W76! id1C4007220E +180fpm +0.0rot')

        mocker.spy(parser.Parser, '_parse_protocol_specific')
        data = parser.Parser.parse_message(msg)
        parser.Parser._parse_protocol_specific.assert_called_once_with(
            '!W76! id1C4007220E +180fpm +0.0rot')

        assert data['raw'] == msg

    def test_parse_msg_delete_update(self, mocker):
        msg = ('NAV07220E>OGNAVI,qAS,NAVITER:/125447h4557.77N/01220.19E\'258/'
               '056/A=006562 !W76! id1C4007220E +180fpm +0.0rot')

        data = {'_update': [{'target': 'key', 'function': lambda x: x}]}

        mocker.patch('ogn_lib.parser.Parser._parse_protocol_specific',
                     return_value=data)
        mocker.patch('ogn_lib.parser.Parser._update_data')

        parser.Parser.parse_message(msg)
        assert parser.Parser._update_data.call_count == 1

    def test_parse_msg_comment(self, mocker):
        mocker.patch('ogn_lib.parser.Parser._parse_protocol_specific',
                     return_value={'comment': True})

        data = parser.Parser.parse_message(
            'FLRDD83BC>APRS,qAS,EDLF:/163148h5124.56N/00634.42E\''
            '276/075/A=001551 [comment]')
        parser.Parser._parse_protocol_specific.assert_called_once_with('[comment]')

        assert data['comment']

    def test_parse_digipeaters(self):
        data = parser.Parser._parse_digipeaters('qAS,RECEIVER')
        assert data == {
            'relayer': None,
            'receiver': 'RECEIVER'
        }

    def test_parse_digipeaters_relayed(self):
        data = parser.Parser._parse_digipeaters('RELAYER*,qAS,RECEIVER')
        assert data == {
            'relayer': 'RELAYER',
            'receiver': 'RECEIVER'
        }

    def test_parse_digipeaters_unknown_format(self):
        with pytest.raises(ValueError):
            parser.Parser._parse_digipeaters('qAS')

    def test_parse_heading_speed(self):
        data = parser.Parser._parse_heading_speed('100', '050')
        assert data['heading'] == 100
        assert abs(data['ground_speed'] - 25.72) < 0.1

    def test_parse_heading_speed_both_missing(self):
        data = parser.Parser._parse_heading_speed('000', '000')
        assert data['heading'] is None
        assert data['ground_speed'] is None

    def test_parse_heading_speed_null_input(self):
        assert not parser.Parser._parse_heading_speed(None, '000')
        assert not parser.Parser._parse_heading_speed('000', None)
        assert not parser.Parser._parse_heading_speed(None, None)

    def test_parse_altitude(self):
        assert abs(parser.Parser._parse_altitude('005000') - 1524) < 1

    def test_parse_altitude_missing(self):
        assert parser.Parser._parse_altitude(None) is None

    def test_parse_attrs(self):
        pass

    def test_parse_timestamp_h(self, mocker):
        with mocker.patch('ogn_lib.parser.Parser._parse_time'):
            parser.Parser._parse_timestamp('010203h')
            parser.Parser._parse_time.assert_called_once_with('010203')

    def test_parse_timestamp_z(self, mocker):
        with mocker.patch('ogn_lib.parser.Parser._parse_datetime'):
            parser.Parser._parse_timestamp('010203z')
            parser.Parser._parse_datetime.assert_called_once_with('010203')

    def test_parse_time_past(self):
        for i in range(24):
            now = datetime.utcnow()
            other = now - timedelta(hours=i)
            parsed = parser.Parser._parse_time(other.strftime('%H%M%S'))

            delta = (now - parsed).total_seconds()
            assert 0 <= delta <= 86400

    def test_parse_time_future(self):
        for i in range(5):
            now = datetime.utcnow()
            other = now + timedelta(minutes=i)
            parsed = parser.Parser._parse_time(other.strftime('%H%M%S'))

            delta = (parsed - now).total_seconds()
            assert (i - 1) * 60 <= delta <= i * 60

    def test_parse_datetime(self):
        now = datetime.utcnow()
        parsed = parser.Parser._parse_datetime(now.strftime('%d%H%M'))

        assert (parsed - now).total_seconds() < 60

    def test_parse_location_sign(self):
        assert parser.Parser._parse_location('0100.00N') >= 0
        assert parser.Parser._parse_location('00100.00E') >= 0
        assert parser.Parser._parse_location('0100.00S') < 0
        assert parser.Parser._parse_location('00100.00W') < 0

    def test_parse_location_value(self):
        val = parser.Parser._parse_location('0130.50N')
        assert abs(val - 1.5083333) < 0.0001
        val = parser.Parser._parse_location('01125.01W')
        assert abs(val - -11.416833) < 0.0001

    def test_parse_protocol_specific(self):
        assert parser.Parser._parse_protocol_specific("1 2 3 4") == {}

    def test_get_location_update_func(self):
        fn = parser.Parser._get_location_update_func(0)
        assert 1 == fn(1)

    def test_update_location_decimal_same(self):
        existing = 1
        new = parser.Parser._update_location_decimal(existing, 0)
        assert new == existing

    def test_update_location_decimal_positive(self):
        existing = 1
        new = parser.Parser._update_location_decimal(existing, 3)
        assert new > existing

    def test_update_location_decimal_negative(self):
        existing = -1
        new = parser.Parser._update_location_decimal(existing, 3)
        assert new < existing

    def test_call(self, mocker):
        msg = 'FLR123456>APRS,reminder_of_message'
        with mocker.patch('ogn_lib.parser.APRS.parse_message'):
            parser.Parser(msg)
            parser.APRS.parse_message.assert_called_once_with(msg)

    def test_update_data(self):
        updates = [
            {'target': 'key1', 'function': lambda x: 0},
            {'target': 'key2', 'function': lambda x: x - 1}
        ]
        data = {
            'key1': 1,
            'key2': 2
        }

        assert parser.Parser._update_data(data, updates) == {
            'key1': 0,
            'key2': 1
        }

    def test_update_data_missing(self):
        # following should pass:
        parser.Parser._update_data({}, [{'target': 'key',
                                         'function': lambda x: x}])


class TestAPRS:

    def test_parse_protocol_specific(self):
        msg = ('!W12! id06DF0A52 +020fpm +0.0rot FL000.00 55.2dB 0e -6.2kHz'
               ' gps4x6 s6.01 h03 rDDACC4 +5.0dBm hearD7EA hearDA95')
        data = parser.APRS._parse_protocol_specific(msg)
        assert len(data['_update']) == 2
        assert (set(map(lambda x: x['target'], data['_update'])) ==
                {'latitude', 'longitude'})
        del data['_update']
        assert data == {
            'address_type': constants.AddressType.flarm,
            'aircraft_type': constants.AirplaneType.glider,
            'do_not_track': False,
            'error_count': 0,
            'flarm_hardware': 3,
            'flarm_id': 'DDACC4',
            'flarm_software': '6.01',
            'flight_level': 0.0,
            'frequency_offset': -6.2,
            'gps_quality': {'horizontal': 4, 'vertical': 6},
            'other_devices': ['D7EA', 'DA95'],
            'power_ratio': 5.0,
            'signal_to_noise_ratio': 55.2,
            'stealth': False,
            'turn_rate': 0.0,
            'uid': '06DF0A52',
            'vertical_speed': 6.096
        }

    def test_parse_id_string(self):
        uid = '06DF0A52'

        data = parser.APRS._parse_id_string(uid)
        assert data['uid'] == uid
        assert not data['stealth']
        assert not data['do_not_track']
        assert data['aircraft_type'] is constants.AirplaneType.glider
        assert data['address_type'] is constants.AddressType.flarm


class TestNaviter:

    def test_parse_protocol_specific(self):
        msg = '!W76! id1C4007220E +180fpm +0.0rot'
        data = parser.Naviter._parse_protocol_specific(msg)
        assert len(data['_update']) == 2
        assert (set(map(lambda x: x['target'], data['_update'])) ==
                {'latitude', 'longitude'})
        del data['_update']
        assert data == {
            'address_type': constants.AddressType.naviter,
            'aircraft_type': constants.AirplaneType.paraglider,
            'do_not_track': False,
            'stealth': False,
            'turn_rate': 0.0,
            'uid': '1C4007220E',
            'vertical_speed': 54.864000000000004
        }

    def test_parse_id_string(self):
        uid = '1C4007220E'

        data = parser.Naviter._parse_id_string(uid)
        assert data['uid'] == uid
        assert not data['stealth']
        assert not data['do_not_track']
        assert data['aircraft_type'] is constants.AirplaneType.paraglider
        assert data['address_type'] is constants.AddressType.naviter


class TestSpot:
    def test_parse_protocol_specific(self):
        data = parser.Spot._parse_protocol_specific('id0-2860357 SPOT3 GOOD')
        assert data['id'] == 'id0-2860357'
        assert data['model'] == 'SPOT3'
        assert data['status'] == 'GOOD'

    def test_parse_protocol_specific_fail(self):
        with pytest.raises(exceptions.ParseError):
            parser.Spot._parse_protocol_specific('id0-2860357 SPOT3')


class TestServerParser:

    def test_parse_message_beacon(self, mocker):
        msg = ('LKHS>APRS,TCPIP*,qAC,GLIDERN2:/211635h4902.45NI01429.51E&'
               '000/000/A=001689')

        data = parser.ServerParser.parse_message(msg)
        assert data['from'] == 'LKHS'
        assert data['destto'] == 'APRS'
        assert data['timestamp'].time() == time(21, 16, 35)
        assert data['latitude'] == 49.04083333333333
        assert data['longitude'] == 14.491833333333334
        assert not data['heading']
        assert not data['ground_speed']
        assert abs(data['altitude'] - 514.8) < 1
        assert data['raw'] == msg
        assert data['beacon_type'] == constants.BeaconType.server_beacon
        assert 'comment' not in data

    def test_parse_message_status(self, mocker):
        msg = (
            'LKHS>APRS,TCPIP*,qAC,GLIDERN2:/211635h v0.2.6.ARM CPU:0.2 '
            'RAM:777.7/972.2MB NTP:3.1ms/-3.8ppm 4.902V 0.583A +33.6C 14/'
            '16Acfts[1h] RF:+62-0.8ppm/+33.66dB/+19.4dB@10km[112619]/+25.0'
            'dB@10km[8/15]')

        data = parser.ServerParser.parse_message(msg)
        assert data['from'] == 'LKHS'
        assert data['destto'] == 'APRS'
        assert data['timestamp'].time() == time(21, 16, 35)
        assert not data['latitude']
        assert not data['longitude']
        assert 'heading' not in data
        assert 'ground_speed' not in data
        assert not data['altitude']
        assert data['raw'] == msg
        assert data['beacon_type'] == constants.BeaconType.server_status
        assert data['raw']
        assert data['comment'].startswith('v0.2.6')

    def test_parse_beacon_comment(self, mocker):
        msg = ('LKHS>APRS,TCPIP*,qAC,GLIDERN2:/211635h4902.45NI01429.51E&'
               '000/000/A=001689 comment')
        data = parser.ServerParser.parse_message(msg)

        assert data['comment'] == 'comment'
