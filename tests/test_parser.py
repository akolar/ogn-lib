import pytest
from datetime import datetime, timedelta
from ogn_lib import exceptions, parser


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
            __destto__ = ['CALL1234', 'CALL4321']

        assert 'CALL1234' in parser.ParserBase.parsers
        assert 'CALL4321' in parser.ParserBase.parsers

    def test_new_wrong_id(self):
        with pytest.raises(TypeError):
            class Callsign(parser.Parser):
                __destto__ = 12345678

    def test_call(self, mocker):
        class Callsign(parser.Parser):
            __destto__ = 'CALLSIGN'

            parse_message = mocker.Mock()

        msg = ('FLRDD83BC>CALLSIGN,qAS,EDLF:/163148h5124.56N/00634.42E\''
               '276/075/A=001551')
        parser.ParserBase.__call__(msg)

        Callsign.parse_message.assert_called_once_with(msg)

    def test_call_no_parser(self):
        with pytest.raises(exceptions.ParserNotFoundError):
            parser.ParserBase.__call__(
                'FLRDD83BC>APRS-1,qAS,EDLF:/163148h5124.56N/00634.42E\''
                '276/075/A=001551')


class TestParser:
    def test_parse_msg_from(self, mocker):
        with mocker.patch('ogn_lib.parser.Parser._parse_header', return_value={}):
            data = parser.Parser.parse_message('FROM12345>payload')
            assert data['from'] == 'FROM12345'

    def test_parse_msg(self, mocker):
        with mocker.patch('ogn_lib.parser.Parser._parse_header',
                          return_value={}):
            with mocker.patch('ogn_lib.parser.Parser._parse_comment',
                              return_value={}):

                parser.Parser.parse_message(
                    'FLRDD83BC>APRS,qAS,EDLF:/163148h5124.56N/00634.42E\''
                    '276/075/A=001551')
                parser.Parser._parse_comment.assert_not_called()
                parser.Parser._parse_header.assert_called_once_with(
                    'APRS,qAS,EDLF:/163148h5124.56N/00634.42E\'276/075/A=001551')

    def test_parse_msg_comment(self, mocker):
        with mocker.patch('ogn_lib.parser.Parser._parse_header',
                          return_value={}):
            with mocker.patch('ogn_lib.parser.Parser._parse_comment',
                              return_value={}):

                parser.Parser.parse_message(
                    'FLRDD83BC>APRS,qAS,EDLF:/163148h5124.56N/00634.42E\''
                    '276/075/A=001551 [comment]')
                parser.Parser._parse_comment.assert_called_once_with('[comment]')

    def test_parse_header(self, mocker):
        with mocker.patch('ogn_lib.parser.Parser._parse_origin',
                          return_value={'a': 1}):
            with mocker.patch('ogn_lib.parser.Parser._parse_position',
                              return_value={'b': 2}):
                data = parser.Parser._parse_header('origin:/position')

                parser.Parser._parse_origin.assert_called_once_with('origin')
                parser.Parser._parse_position.assert_called_once_with('position')
                assert data == {'a': 1, 'b': 2}

    def test_parse_origin(self):
        data = parser.Parser._parse_origin('FMT-VERS,qAS,RECEIVER')
        assert data == {
            'destto': 'FMT-VERS',
            'relayer': None,
            'receiver': 'RECEIVER'
        }

    def test_parse_origin_relayed(self):
        data = parser.Parser._parse_origin('FMT-VERS,RELAYER*,qAS,RECEIVER')
        assert data == {
            'destto': 'FMT-VERS',
            'relayer': 'RELAYER',
            'receiver': 'RECEIVER'
        }

    def test_parse_origin_unknown_format(self):
        with pytest.raises(ValueError):
            parser.Parser._parse_origin('FMT-VERS,qAS')

    def test_parse_position(self, mocker):
        c_time = datetime(2017, 1, 1, 1, 2, 3)
        with mocker.patch('ogn_lib.parser.Parser._parse_timestamp',
                          return_value=c_time):
            data = parser.Parser._parse_position(
                '010203h0100.00N/00200.00\'200/100/A=00042')

        assert data['timestamp'] == c_time
        assert data['latitude'] == 1
        assert data['longitude'] == 2
        assert data['heading'] == 200
        assert abs(data['ground_speed'] - 51.44447) < 0.01
        assert abs(data['altitude'] - 12.8016) < 0.01

    def test_parse_position_no_hdg_speed(self):
        data = parser.Parser._parse_position(
            '010203h0100.00N/00200.00\'000/000/A=00042')

        assert data['heading'] is None
        assert data['ground_speed'] is None

    def test_parse_timestamp_past(self):
        for i in range(24):
            now = datetime.utcnow()
            other = now - timedelta(hours=i)
            parsed = parser.Parser._parse_timestamp(other.strftime('%H%M%S'))

            delta = (now - parsed).total_seconds()
            assert 0 <= delta <= 86400

    def test_parse_timestamp_future(self):
        for i in range(5):
            now = datetime.utcnow()
            other = now + timedelta(minutes=i)
            parsed = parser.Parser._parse_timestamp(other.strftime('%H%M%S'))

            delta = (parsed - now).total_seconds()
            assert (i - 1) * 60 <= delta <= i * 60

    def test_parse_location_sign(self):
        assert parser.Parser._parse_location('0100.00N') >= 0
        assert parser.Parser._parse_location('00100.00E') >= 0
        assert parser.Parser._parse_location('0100.00S') < 0
        assert parser.Parser._parse_location('00100.00W') < 0

    def test_parse_location_value(self):
        val = parser.Parser._parse_location('0130.50N')
        assert abs(val == 1.5083333) < 0.0001
        val = parser.Parser._parse_location('01125.01W')
        assert abs(val - -11.416833) < 0.0001

    def test_parse_comment(self):
        assert parser.Parser._parse_comment("1 2 3 4") == {}
