"""
ogn_lib.client
--------------

This module contains methods and classes related to opening and managing a
connection to OGN's APRS servers.
"""

import logging
import socket
import time

import ogn_lib


logger = logging.getLogger(__name__)


class OgnClient:
    """
    Holds an APRS session.

    Provides methods for listening to received messages and managing
    the session.
    """

    APRS_SERVER = 'aprs.glidernet.org'
    APRS_PORT_FULL = 10152
    APRS_PORT_FILTER = 14580
    SOCKET_KEEPALIVE = 240

    def __init__(self, username, passcode='-1', server=None, port=None,
                 filter_=None):
        """
        Creates a new OgnClient instance.

        :param str username: username used for logging in the APRS system
        :param str passcode: a valid passcode for given `username`
        :param server: an optional addres of an APRS server (defaults to
                       aprs.glidernet.org)
        :type server: str or None
        :param port: optional port of the APRS server (defaults to 10152 or
                     14580)
        :type port: int or None
        :param filter_: optional `filter` parameter to be passed to the APRS
                        server
        :type filter_: str or None
        """

        self.username = username
        self.passcode = passcode
        self.server = server or self.APRS_SERVER
        self.port = port or (self.APRS_PORT_FILTER if filter_
                             else self.APRS_PORT_FULL)
        self.filter_ = filter_
        self._authenticated = False
        self._kill = False
        self._last_send = -1
        self._connection_retries = 50

    def connect(self):
        """
        Opens a socket connection to the APRS server and authenticates the
        client.

        :raise ogn_lib.exceptions.LoginError: if an authentication error has
                                              occured
        """

        logger.info('Connecting to %s:%d as %s:%s. Filter: %s',
                    self.server, self.port, self.username, self.passcode,
                    self.filter_ if self.filter_ else 'not set')

        self._socket = socket.create_connection((self.server, self.port))
        self._socket.settimeout(15)

        self._sock_file = self._socket.makefile()
        conn_response = self._sock_file.readline().strip()
        logger.debug('Connection response: %s', conn_response)

        auth = self._gen_auth_message()
        logger.debug('Sending authentication message: %s', auth)

        self.send(auth)
        login_status = self._sock_file.readline().strip()
        logger.debug('Login status: %s', login_status.strip())

        try:
            self._authenticated = self._validate_login(login_status)
        except (ogn_lib.exceptions.LoginError,
                ogn_lib.exceptions.ParseError) as e:
            logger.exception(e)
            logger.fatal('Failed to authenticate')
            self._sock_file.close()
            self._socket.close()
            logger.info('Socket closed')
            raise

        self._kill = False

    def disconnect(self):
        logger.info('Disconnecting from the server')
        self._kill = True
        self._sock_file.close()
        self._socket.close()

    def receive(self, callback, reconnect=True, parser=None):
        """
        Receives the messages received from the APRS stream and passes them to
        the callback function.

        :param callback: the callback function which takes one parameter
                         (the received message)
        :type callback: callable
        :param bool reconnect: True if the client should automatically restart
                               after the connection drops
        :param parser: function that parses the APRS messages or None if
                       callback should receive raw messages
        :type parser: callable or None
        """

        # The client might be ran for extended periods of time. Although using
        # a recursive call to enter the inner for loop would be considered
        # a "nicer" solution, it would also have the potential to _eventually_
        # exceed the maximum recursion depth (in cPython, other implementations
        # might support tail optimized calls).
        # This is why this function is written with a double while loop.
        while not self._kill:
            try:
                self._receive_loop(callback, parser)
            except (BrokenPipeError, ConnectionResetError, socket.error,
                    socket.timeout) as e:
                logger.error('Socket connection dropped')
                logger.exception(e)

            if self._kill or not reconnect:
                logger.info('Exiting OgnClient.receive()')
                return

            self._reconnect(retries=self._connection_retries, wait_period=15)

    def _reconnect(self, retries=1, wait_period=15):
        """
        Attempts to recover a failed server connection.

        :param int retries: number of times reestablishing connection is
            attempted
        :param float wait_period: amount of seconds between two sequential
            retries
        """

        logger.info('Trying to reconnect...')

        while retries > 0:
            try:
                self.connect()
                logger.error('Successfully reconnected')
                break
            except (BrokenPipeError, ConnectionResetError, socket.error,
                    socket.timeout) as e:
                logger.error('Reconnection attempt failed')
                logger.exception(e)
                retries -= 1
                time.sleep(wait_period)
        else:
            raise ConnectionError

    def _receive_loop(self, callback, parser):
        """
        The main loop of the receive function.

        :param callback: the callback function which takes one parameter
                         (the received message)
        :type callback: callable
        :param parser: function that parses the APRS messages or None if
                       callback should receive raw messages
        :type parser: callable or None
        """

        line = None
        while line != '' and not self._kill:
            line = self._sock_file.readline().strip()
            logger.debug('Received APRS message: %s', line)

            if line.startswith('#'):
                logger.debug('Received server message: %s', line)
            elif parser:
                try:
                    callback(parser(line))
                except ogn_lib.exceptions.ParseError as e:
                    logger.exception(e)
            else:
                logger.debug('Returning raw APRS message to callback')
                callback(line)

            self._keepalive()

    def send(self, message, retries=0, wait_period=0):
        """
        Sends the message to the APRS server.

        :param str message: message to be sent
        """

        try:
            message_nl = message.strip('\n') + '\n'
            logger.info('Sending: %s', message_nl)
            self._socket.sendall(message_nl.encode())
            self._last_send = time.time()
        except (BrokenPipeError, ConnectionResetError, socket.error,
                socket.timeout):
            if retries < 3:
                self._reconnect(retries=3, wait_period=wait_period)
                self.send(message, retries=retries + 1)
            else:
                raise

    def _keepalive(self):
        """
        Sends the keep alive message to APRS server (if necessary).
        """

        td = time.time() - self._last_send

        if td > self.SOCKET_KEEPALIVE:
            logger.info('No messages sent for %.0f seconds; sending keepalive',
                        td)
            self.send('#keepalive')

    def _gen_auth_message(self):
        """
        Generates an APRS authentication message.

        :return: authentication message
        :rtype: str
        """

        base = 'user {} pass {} vers {} {}'.format(self.username,
                                                   self.passcode,
                                                   ogn_lib.__title__,
                                                   ogn_lib.__version__)

        if self.filter_:
            base += ' filter {}'.format(self.filter_)

        return base

    def _validate_login(self, message):
        """
        Verifies that the login to the APRS server was successful.

        :param str message: authentication response from the server
        :return: True if user is authenticated to send messages
        :rtype: bool
        :raises ogn_lib.exceptions.LoginError: if the login was unsuccessful
        """

        # Sample response: # logresp user unverified, server GLIDERN3
        if not message.startswith('# logresp'):
            raise ogn_lib.exceptions.LoginError(
                'Not a login message: ' + message)

        try:
            user_info, serv_info = message.split(', ')
            username, status = user_info[10:].split(' ')
            server = serv_info[7:]
        except (IndexError, ValueError):
            raise ogn_lib.exceptions.ParseError(
                'Unable to parse login message: ' + message)

        authenticated = False
        if status == 'verified':
            authenticated = True
            logger.info('Successfully connected to %s as %s', server, username)
        elif status == 'unverified' and self.passcode != '-1':
            logger.info('Connected to %s', server)
            logger.warn('Wrong username/passcode, continuing in r/o mode')
        elif status == 'unverified':
            logger.info('Connected to %s as guest', server)
        else:
            raise ogn_lib.exceptions.LoginError('Login failed: ' + message)

        return authenticated
