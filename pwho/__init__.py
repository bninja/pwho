"""
PROXY protocol v1:

- http://www.haproxy.org/download/1.5/doc/proxy-protocol.txt

parsing *taken* from:

- https://github.com/benoitc/gunicorn/

Use it e.g.  with ``SocketServer`` like:

.. code:: python

    import SocketServer
    
    import pwho
    
    class SFTPRequestHandler(
              SocketServer.StreamRequestHandler,
              pwh.StreamRequestMixin
          ):
    
        def handle(self)
            proxy_info = self.proxy_protocol(
                error='unread', limit=4096, default='peer'
            )
            print proxy_info
            ...

"""
__version__ = '0.1.0'

__all__ = [
    'ProxyInfo',
    'StreamRequestMixin',
    'parse_line',
    'exc',
]

import collections
import io
import logging
import os
import socket

from . import exc

logger = logging.getLogger(__name__)


ProxyInfo = collections.namedtuple('ProxyInfo', [
    'source_address',
    'source_port',
    'destination_address',
    'destination_port',
])


class StreamRequestMixin(object):
    """
    `SocketServer.StreamRequestHandler` mixin for adding PROXY protocol
    parsing, e.g.:
    
    .. code:: python
    
        import netaddr
        import pwho
    
        class MyRequestHandler(
                  SocketServer.StreamRequestHandler, pwho.StreamRequestMixin
              ):
    
            def proxy_authenticate(self, info):
                if not super(MyRequestHandler, self).proxy_authenticate(info):
                    return False
                destination_ip = netaddr.IPAddress(info.destination_address)
                return destination_ip in netaddr.IPNetwork('10/8')
    
            def handle(self)
                proxy_info = self.proxy_protocol(default='peer', authenticate=True)
                ...
    
    """

    def proxy_authenticate(self, info):
        """
        Authentication hook for parsed proxy information. Defaults to ensuring
        destination (i.e. proxy) is the peer.
        
        :param info: Parsed ``ProxyInfo`` instance.
        
        :returns: ``True`` if authenticated, otherwise ``False``.
        """
        return (info.destination_address, info.destination_port) == self.client_address

    def proxy_protocol(self, error='raise', default=None, limit=None, authenticate=False):
        """
        Parses, and optionally authenticates, proxy protocol information from
        request. Note that ``self.request`` is wrapped by ``SocketBuffer``.
        
        :param error:
            How read (``exc.ReadError``) and parse (``exc.ParseError``) are
            handled, one of:
            - "raise" to propagate.
            - "unread" to suppress exceptions and unread back to socket.
        :param default:
            What to return when no ``ProxyInfo`` was found. Only meaningful
            with error "unread".
        :param limit:
            Maximum number of bytes to read when probing request for
            ``ProxyInfo``.
        
        :returns: Parsed ``ProxyInfo`` instance or **default** if none found.
        """
        if error not in ('raise', 'unread'):
            raise ValueError('error="{0}" is not  "raise" or "unread""')
        if not isinstance(self.request, SocketBuffer):
            self.request = SocketBuffer(self.request)
        if default == 'peer':
            default = ProxyInfo(
                self.client_address[0], self.client_address[1],
                self.client_address[0], self.client_address[1],
            )
        try:
            line = read_line(
                self.request.sock,
                self.request.buf,
                limit=limit,
            )
        except exc.ReadError:
            if error == 'raise':
                raise
            return default
        try:
            info = parse_line(line)
        except exc.ParseError:
            if error == 'raise':
                raise
            self.request.unread(line)
            return default
        if authenticate and not self.proxy_authenticate(info):
            logger.info('authentication failed - %s', info)
            return default
        return info


class SocketBuffer(object):

    def __init__(self, sock):
        self.sock = sock
        self.buf = io.BytesIO()
        for delegate in ['send', 'shutdown', 'getpeername']:
            setattr(self, delegate, getattr(self.sock, delegate))

    def unread(self, bytes):
        data = bytes + self.buf.getvalue()
        self.buf.seek(0)
        self.buf.write(data)

    # socket.Socket

    def recv(self, bufsize, flags=0):
        if not self.buf.tell():
            return self.sock.recv(bufsize, flags)
        data = self.buf.getvalue()
        self.buf.seek(0)
        if len(data) > bufsize:
            head = data[:bufsize]
            self.buf.write(data[bufsize:])
            data = head
        self.buf.truncate()
        return data

    def recvfrom(self, bufsize, flags=0):
        if not self.buf.tell():
            return self.sock.recvfrom(bufsize, flags)
        address = self.sock.getpeername()
        return (self.recv(bufsize, flags), address)

    def recv_into(self, buffer, nbytes=0, flags=0):
        if not self.buf.tell():
            return self.sock.recv_into(buffer, nbytes, flags)
        data = self.recv(nbytes or len(buffer), flags)
        buffer.write(data)
        return len(data)

    def recvfrom_into(self, buffer, nbytes=0, flags=0):
        if not self.buf.tell():
            return self.sock.recvfrom_into(buffer, nbytes, flags)
        address = self.sock.getpeername()
        return (self.recv_into(buffer, nbytes, flags), address)

    def send(self, *args, **kwargs):
        return self.sock.send(*args, **kwargs)

    def close(self):
        self.buf.seek(0)
        self.buf.truncate()
        return self.sock.close()


CRLF = b'\r\n'


def read_line(sock, buffer, read_size=256, limit=None):
    while True:
        data = buffer.getvalue()
        idx = data.find(CRLF)
        if idx >= 0:
            if limit and idx + 2 > limit:
                raise exc.LineTooLong(idx, limit)
            line = data[:idx + 2]
            buffer.seek(0)
            buffer.write(data[idx + 2:])
            buffer.truncate()
            return line
        elif limit and len(data) + 2 > limit:
            raise exc.LineTooLong(len(data), limit)
        data = sock.recv(read_size)
        if not data:
            raise exc.NoLine(len(buffer.getvalue()))
        buffer.write(data)


def parse_line(line):
    """
    Parses a byte string like:
    
       PROXY TCP4 192.168.0.1 192.168.0.11 56324 443\r\n
    
    to a `ProxyInfo`.
    """
    if not line.startswith(b'PROXY'):
        raise exc.InvalidLine('Missing "PROXY" prefix', line)
    if not line.endswith(CRLF):
        raise exc.InvalidLine('Missing "\\r\\n" terminal', line)
    parts = line[:-len(CRLF)].split(b' ')
    if len(parts) != 6:
        raise exc.InvalidLine('Expected 6 " " delimited parts', line)

    inet, src_addr, dst_addr = parts[1:4]
    if inet == b'TCP4':
        try:
            socket.inet_pton(socket.AF_INET, src_addr)
            socket.inet_pton(socket.AF_INET, dst_addr)
        except socket.error:
            raise exc.InvalidLine('Invalid INET {0} address(es)'.format(inet), line)
    elif inet == b'TCP6':
        try:
            socket.inet_pton(socket.AF_INET6, src_addr)
            socket.inet_pton(socket.AF_INET6, dst_addr)
        except socket.error:
            raise exc.InvalidLine('Invalid INET {0} address(es)'.format(inet), line)
    else:
        raise exc.InvalidLine('Unsupported INET "{0}"'.format(inet), line)
    try:
        src_port = int(parts[4])
        dst_port = int(parts[5])
    except (TypeError, ValueError):
        raise exc.InvalidLine(line, 'Invalid port')

    return ProxyInfo(
        source_address=src_addr,
        source_port=src_port,
        destination_address=dst_addr,
        destination_port=dst_port,
    )
