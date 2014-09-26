====
pwho
====

.. image:: https://travis-ci.org/bninja/pwho.png
   :target: https://travis-ci.org/bninja/pwho

.. image:: https://coveralls.io/repos/bninja/pwho/badge.png
   :target: https://coveralls.io/r/bninja/pwho

PROXY protocol v1:

- http://www.haproxy.org/download/1.5/doc/proxy-protocol.txt

parsing **taken** from:

- https://github.com/benoitc/gunicorn/

Get it:

.. code:: bash

   $ pip install pwho
    
Use it e.g.  with ``SocketServer`` like:

.. code:: python

    import SocketServer
    
    import pwho

    class SFTPRequestHandler(
              SocketServer.StreamRequestHandler,
              pwho.StreamRequestMixin
          ):
    
        def handle(self)
            self.proxy_info = self.proxy_protocol(error='unread', authenticate=True)
            ...
