"""
ogn_lib.client
--------------

This module contains methods and classes related to opening and managing a
connection to OGN's APRS servers.
"""

import logging
import socket

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

    def receive(self, callback, reconnect=True, raw=False):
        """
        Receives the messages received from the APRS stream and passes them to
        the callback function.

        :param callback: the callback function which takes one parameter
                         (the received message)
        :type callback: callable
        :param bool reconnect: True if the client should automatically restart
                               after the connection drops
        :param bool raw: True if callback should be passed raw APRS messages
                         instead of parsed objects
        """

        line = self._sock_file.readline().strip()
        while line != '':
            logger.debug('Received APRS message: %s', line)
            line = self._sock_file.readline().strip()

    def send(self, message):
        """
        Sends the message to the APRS server.

        :param str message: message to be sent
        """

        message_nl = message.strip('\n') + '\n'
        logger.info('Sending: %s', message_nl)
        self._socket.sendall(message_nl.encode())

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
