import pytest
from ogn_lib import client, exceptions


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

    def _get_mocked_socket(self, mocker):
        sock_file = mocker.MagicMock()
        sock_file.readline = mocker.MagicMock(side_effect=[
            '# aprsc 2.1.4-g408ed49',
            '# logresp user verified, server GLIDERN3'
        ])

        socket = mocker.MagicMock()
        socket.makefile = mocker.MagicMock(return_value=sock_file)

        return socket
