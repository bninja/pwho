__all__ = [
    'ReadError',
    'LineTooLong',
    'NoLine',
    'ParseError',
    'InvalidLine',
]


class ReadError(Exception):

    pass


class LineTooLong(ReadError):

    def __init__(self, length, limit):
        super(LineTooLong, self).__init__(
            'Read {0} bytes > {1} before reaching "\\r\\n" terminal'
            .format(length, limit)
        )
        self.length = length
        self.limit = limit


class NoLine(ReadError):

    def __init__(self, size):
        super(NoLine, self).__init__(
            'Read {0} bytes before reaching "\\r\\n" terminal'.format(size)
        )
        self.size = size


class ParseError(Exception):

    pass


class InvalidLine(ParseError):

    def __init__(self, reason, line):
        super(InvalidLine, self).__init__('{0} - {1}'.format(reason, line))
        self.line = line
