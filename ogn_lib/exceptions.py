class LoginError(Exception):
    """
    An error occurred when logging in.
    """

    pass


class ParseError(Exception):
    """
    An error occurred when trying to parse the message.
    """

    pass


class ParserNotFoundError(Exception):
    """
    Parser for the given destto name was not registered with the meta class.
    """

    pass
