import io
import socket
import SocketServer
import threading

import netaddr
import pytest

import pwho


def read_line(sock, buf):
    while True:
        data = buf.getvalue()
        idx = data.find(pwho.CRLF)
        if idx >= 0:
            line = data[:idx + 2]
            buf.seek(0)
            buf.write(data[idx + 2:])
            buf.truncate()
            return line
        data = sock.recv(4096)
        if not data:
            raise pwho.exc.NoLine(len(buf.getvalue()))
        buf.write(data)


def hander(error):

    class RequestHandler(
              SocketServer.StreamRequestHandler,
              pwho.StreamRequestMixin,
          ):

        def handle(self):
            proxy_info = self.proxy_protocol(error=error, limit=1024)
            msg = []
            buf = io.BytesIO()
            if proxy_info is None:
                msg.append(read_line(self.request, buf))
            else:
                msg.append(b','.join(map(str, proxy_info)))
                msg.append(pwho.CRLF)
            msg.append(read_line(self.request, buf))
            for frag in msg:
                self.request.send(frag)

    return RequestHandler


def stream_ping(address, proxy_line, msg):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(address)

    sock.send(proxy_line)
    sock.send(pwho.CRLF)
    sock.send(msg)
    sock.send(pwho.CRLF)

    buf = io.BytesIO()
    return (
        read_line(sock, buf)[:-len(pwho.CRLF)],
        read_line(sock, buf)[:-len(pwho.CRLF)]
    )


@pytest.fixture(scope='session')
def unread_stream_server(request):
    server = SocketServer.ThreadingTCPServer(
        ('localhost', 0), hander('unread')
    )
    threading.Thread(target=server.serve_forever).start()
    request.addfinalizer(server.shutdown)
    return server


@pytest.fixture(scope='session')
def raise_stream_server(request):
    server = SocketServer.ThreadingTCPServer(
        ('localhost', 0), hander('raise')
    )
    threading.Thread(target=server.serve_forever).start()
    request.addfinalizer(server.shutdown)
    return server


def test_alls():
    from pwho import *
    from pwho.exc import *


@pytest.mark.parametrize('line, expected', [
    (b'', 'Missing "PROXY" prefix'),
    (pwho.CRLF, 'Missing "PROXY" prefix'),
    (b'PROXY', 'Missing "\\r\\n" terminal'),
    (b'PROXY UNKNOWN\r\n', 'Expected 6 " " delimited parts'),
    (b'PROXY TCP4 sry 192.168.0.11 56324 443\r\n', ''),
    (b'PROXY TCP4 192.168.0.1 192.168.0.11 56324 443\r\n',
     pwho.ProxyInfo(
        '192.168.0.1', 56324,
        '192.168.0.11', 443,
    )),
    (b'PROXY TCP4 192.168.0.1 192.168.0.11 abc 443\r\n', ''),
    (b'PROXY TCP6 FE80:0000:0000:0000:0202:B3FF:FE1E:8329 2607:f0d0:1002:0051:0000:0000:0000:0004 56324 443\r\n',
     pwho.ProxyInfo(
        'FE80:0000:0000:0000:0202:B3FF:FE1E:8329', 56324,
        '2607:f0d0:1002:0051:0000:0000:0000:0004', 443,
    )),
])
def test_parse(line, expected):
    if isinstance(expected, pwho.ProxyInfo):
        assert pwho.parse_line(line) == expected
    else:
        with pytest.raises(pwho.exc.InvalidLine) as exc_info:
            pwho.parse_line(line)
        if isinstance(expected, basestring):
            assert expected in str(exc_info.value)


@pytest.mark.parametrize('line, expected', [
    (b'', b''),
    (b'PROXY UNKNOWN', b'PROXY UNKNOWN'),
    (b'PROXY TCP4 sry 192.168.0.11 56324 443', b'PROXY TCP4 sry 192.168.0.11 56324 443'),
    (b'PROXY TCP4 192.168.0.1 192.168.0.11 56324 443', b'192.168.0.1,56324,192.168.0.11,443'),
    (b'PROXY TCP4 192.168.0.1 192.168.0.11 abc 443', b'PROXY TCP4 192.168.0.1 192.168.0.11 abc 443'),
    (b'PROXY TCP6 FE80:0000:0000:0000:0202:B3FF:FE1E:8329 2607:f0d0:1002:0051:0000:0000:0000:0004 56324 443', b'FE80:0000:0000:0000:0202:B3FF:FE1E:8329,56324,2607:f0d0:1002:0051:0000:0000:0000:0004,443'),
])
def test_unread_stream_request(unread_stream_server, line, expected):
    pong = stream_ping(unread_stream_server.server_address, line, b'hiya')
    assert len(pong), 2
    pl, ml = pong
    assert pl == expected
    assert ml == b'hiya'


def test_unread_stream_request_line_overflow(unread_stream_server):
    pong = stream_ping(unread_stream_server.server_address, '*' * 4096, b'hiya')
    assert len(pong), 2
    pl, ml = pong
    assert pl == '*' * 4096
    assert ml == b'hiya'


@pytest.mark.parametrize('line, expected', [
    (b'', (pwho.exc.NoLine, socket.error)),
    (b'PROXY UNKNOWN', (pwho.exc.NoLine, socket.error)),
    (b'PROXY TCP4 sry 192.168.0.11 56324 443', (pwho.exc.NoLine, socket.error)),
    (b'PROXY TCP4 192.168.0.1 192.168.0.11 56324 443', b'192.168.0.1,56324,192.168.0.11,443'),
    (b'PROXY TCP4 192.168.0.1 192.168.0.11 abc 443', (pwho.exc.NoLine, socket.error)),
    (b'PROXY TCP6 FE80:0000:0000:0000:0202:B3FF:FE1E:8329 2607:f0d0:1002:0051:0000:0000:0000:0004 56324 443', b'FE80:0000:0000:0000:0202:B3FF:FE1E:8329,56324,2607:f0d0:1002:0051:0000:0000:0000:0004,443'),
])
def test_raise_stream_request(raise_stream_server, line, expected):
    if isinstance(expected, basestring):
        pong = stream_ping(raise_stream_server.server_address, line, b'hiya')
        assert len(pong), 2
        pl, ml = pong
        assert pl == expected
        assert ml == b'hiya'
    else:
        with pytest.raises(expected):
            stream_ping(raise_stream_server.server_address, line, b'hiya')


def test_raise_stream_request_line_overflow(raise_stream_server):
    with pytest.raises((socket.error, pwho.exc.NoLine)):
        stream_ping(raise_stream_server.server_address, '*' * 4096, b'hiya')
