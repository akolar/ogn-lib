import time
import pytest
from ogn_lib import client, exceptions

APRS_RECORDS = [
    'FLRDF0F8E>APRS,qAS,EDTD:/075201h4753.35N/00840.21E\'350/063/A=004359 !W69'
    '! id0ADF0F8E +079fpm -0.6rot 21.5dB 0e -9.5kHz gps1x1',
    'FLRDD51B2>APRS,qAS,EDER:/075201h5028.56N/00955.38E\'116/115/A=004139 !W99'
    '! id0ADD51B2 +040fpm +0.0rot 25.8dB 0e -3.6kHz gps3x3',
    'FLRDDEF49>APRS,qAS,EDQE:/075201h4947.60N/01107.66E\'000/000/A=001627 !W51'
    '! id06DDEF49 +000fpm +0.0rot 52.8dB 0e +10.2kHz gps1x1'
]


class TestClient:

    def test_init_set_server(self):
        server = 'example.com'
        cl = client.OgnClient('username', server=server)
        assert cl.server != client.OgnClient.APRS_SERVER
        assert cl.server == server

    def test_init_default_server(self):
        cl = client.OgnClient('username')
        assert cl.server == client.OgnClient.APRS_SERVER

    def test_init_port(self):
        cl = client.OgnClient('username')
        assert cl.port == client.OgnClient.APRS_PORT_FULL

    def test_init_port_filter(self):
        cl = client.OgnClient('username', filter_='filter')
        assert cl.port == client.OgnClient.APRS_PORT_FILTER

    def test_init_port_set(self):
        cl = client.OgnClient('username', port=-1, filter_='filter')
        assert cl.port == -1
        cl = client.OgnClient('username', port=-1)
        assert cl.port == -1

    def test_connect_sock_file(self, mocker):
        sock = self._get_mocked_socket(mocker)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl.connect()
        assert not cl._sock_file.close.called

    def test_connect_reset_kill(self, mocker):
        sock = self._get_mocked_socket(mocker)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl.connect()
        assert not cl._kill

    def test_connect_responses(self, mocker):
        sock = self._get_mocked_socket(mocker)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl.connect()
        assert cl._authenticated

    def test_connect_failed_auth(self, mocker):
        sock = self._get_mocked_socket(mocker)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl._validate_login = mocker.MagicMock(
                side_effect=exceptions.ParseError)

            with pytest.raises(exceptions.ParseError):
                cl.connect()

        cl._sock_file.close.call_count == 1
        cl._socket.close.call_count == 1

    def test_disconnect(self, mocker):
        sock = self._get_mocked_socket(mocker)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl.connect()
            cl.disconnect()

        assert cl._kill
        assert sock.close.call_count > 0
        assert cl._sock_file.close.call_count > 0

    def test_receive_exit(self, mocker):
        sock = self._get_mocked_socket(mocker, True)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl.connect()
            cl.receive(lambda x: cl.disconnect())

        # Only testing if function stops

    def test_receive_reconnect(self, mocker):
        sock = self._get_mocked_socket(mocker, True)
        with mocker.patch('socket.create_connection', return_value=sock):
            with mocker.patch('time.sleep') as m_time:
                cl = client.OgnClient('username')
                cl._receive_loop = mocker.MagicMock(side_effect=BrokenPipeError)
                cl.connect()
                cl.connect = mocker.MagicMock(side_effect=lambda: cl.disconnect())
                cl.receive(lambda x: None)

                m_time.call_count == 0

        assert cl.connect.call_count > 0

    def test_receive_reconnect_fail(self, mocker):
        sock = self._get_mocked_socket(mocker, True)
        with mocker.patch('socket.create_connection', return_value=sock):
            with mocker.patch('time.sleep') as m_time:
                cl = client.OgnClient('username')
                cl._receive_loop = mocker.MagicMock(side_effect=BrokenPipeError)
                cl.connect()
                cl.connect = mocker.MagicMock(side_effect=BrokenPipeError)
                with pytest.raises(ConnectionError):
                    cl.receive(lambda x: None)

                m_time.call_count == cl._connection_retries

        assert cl.connect.call_count == cl._connection_retries

    def test_receive_loop_exit(self, mocker):
        sock = self._get_mocked_socket(mocker, True)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl.connect()
            cl._kill = True
            cl._receive_loop(lambda x: None, None)

        # Only testing if function stops

    def test_receive_loop_parse(self, mocker):
        sock = self._get_mocked_socket(mocker, True)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl.connect()
            cb = mocker.MagicMock(side_effect=lambda x: cl.disconnect())
            cl._receive_loop(cb, None)
            cl._receive_loop(cb, lambda x: x)

    def test_receive_loop_raw(self, mocker):
        sock = self._get_mocked_socket(mocker, True)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl.connect()
            cb = mocker.MagicMock(side_effect=lambda x: cl.disconnect())
            cl._receive_loop(cb, None)

            cb.assert_called_once_with(APRS_RECORDS[0])

    def test_receive_loop_keepalive(self, mocker):
        sock = self._get_mocked_socket(mocker, True)
        with mocker.patch('socket.create_connection', return_value=sock):
            cl = client.OgnClient('username')
            cl._keepalive = mocker.MagicMock()
            cl.connect()
            cb = mocker.MagicMock(side_effect=lambda x: cl.disconnect())
            cl._receive_loop(cb, None)

        assert cl._keepalive.call_count > 0

    def test_send(self, mocker):
        cl = client.OgnClient('username')
        cl._socket = mocker.Mock()
        cl.send('test message')
        cl._socket.sendall.assert_called_once_with(b'test message\n')

    def test_send_strip(self, mocker):
        cl = client.OgnClient('username')
        cl._socket = mocker.Mock()
        cl.send('\n\ntest\nmessage\n\n\n')
        cl._socket.sendall.assert_called_once_with(b'test\nmessage\n')

    def test_send_last_send(self, mocker):
        cl = client.OgnClient('username')
        cl._socket = mocker.Mock()
        cl.send('test message')
        assert time.time() - cl._last_send < 0.001

    def _setup_keepalive_client(self, mocker, ts):
        cl = client.OgnClient('username')
        cl.send = mocker.MagicMock()
        cl._last_send = ts

        return cl

    def test_keepalive_pass(self, mocker):
        cl = self._setup_keepalive_client(mocker, time.time())
        cl._keepalive()
        cl.send.assert_not_called()

    def test_keepalive_send(self, mocker):
        cl = self._setup_keepalive_client(mocker, 0)
        cl._keepalive()
        assert cl.send.call_count > 0

    def test_gen_auth_msg(self):
        cl = client.OgnClient('username')
        msg = cl._gen_auth_message()
        user, username, pass_, passcode, *other = msg.split(' ')

        assert user == 'user'
        assert pass_ == 'pass'
        assert username == 'username'
        assert passcode == '-1'
        assert len(other) == 3

    def test_gen_auth_msg_filter(self):
        cl = client.OgnClient('username', filter_='special_filter')
        msg = cl._gen_auth_message()
        assert msg.endswith('filter special_filter')

    def test_validate_login_success(self):
        cl = client.OgnClient('username', passcode='123456')
        assert cl._validate_login('# logresp user verified, server GLIDERN3')

    def test_validate_login_unauth(self):
        cl = client.OgnClient('username')
        assert not cl._validate_login('# logresp user unverified, '
                                      'server GLIDERN3')

    def test_validate_login_failed_auth(self):
        cl = client.OgnClient('username', passcode='123456')
        assert not cl._validate_login('# logresp user unverified, '
                                      'server GLIDERN3')

    def test_validate_login_error(self):
        cl = client.OgnClient('username', passcode='123456')
        with pytest.raises(exceptions.LoginError):
            assert not cl._validate_login('# logresp user blocked, server '
                                          'GLIDERN3')

    def test_validate_login_not_login(self):
        cl = client.OgnClient('username', passcode='123456')
        with pytest.raises(exceptions.LoginError):
            cl._validate_login('# aprsc 2.1.4-g408ed49')

    def test_validate_login_parse_error(self):
        cl = client.OgnClient('username', passcode='123456')
        with pytest.raises(exceptions.ParseError):
            cl._validate_login('# logresp 2.1.4-g408ed49')

    def _get_mocked_socket(self, mocker, aprs_records=False):
        data = [
            '# aprsc 2.1.4-g408ed49',
            '# logresp user verified, server GLIDERN3'
        ]

        if aprs_records:
            data += APRS_RECORDS

        sock_file = mocker.MagicMock()
        sock_file.readline = mocker.MagicMock(side_effect=data)

        socket = mocker.MagicMock()
        socket.makefile = mocker.MagicMock(return_value=sock_file)

        return socket
