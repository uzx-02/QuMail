"""Cancelable DNS, nonblocking TCP and verified TLS under one setup deadline."""
import errno
import select
import socket
import ssl
from transport.bounded_worker import call


def connect(host,port,budget):
    budget.check()
    if (host,port) in [('imap.gmail.com',993),('smtp.gmail.com',587)]:
        addresses=call(dict(op='dns',host=host,port=port),budget.cancel,budget.deadline)
    elif host=='127.0.0.1':  # Only explicit test factories use this route.
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,0,'',(host,port))]
    else: raise OSError('endpoint rejected')
    for family,kind,protocol,_,address in addresses:
        budget.check(); sock=socket.socket(family,kind,protocol)
        try:
            sock.setblocking(False)
            status=sock.connect_ex(tuple(address))
            if status not in (0,errno.EINPROGRESS,errno.EWOULDBLOCK,errno.EALREADY,10035,10036,10037):
                raise OSError('connect failed')
            while status:
                budget.check()
                _,ready,failed=select.select([],[sock],[sock],.05)
                if ready or failed:
                    if sock.getsockopt(socket.SOL_SOCKET,socket.SO_ERROR): raise OSError('connect failed')
                    break
            budget.check(); return sock
        except OSError:
            sock.close()
        except BaseException:
            sock.close(); raise
    raise OSError('connection failed')


def secure(sock,context,host,budget):
    try:
        if not context.check_hostname or context.verify_mode!=ssl.CERT_REQUIRED: raise OSError('TLS policy')
        sock=context.wrap_socket(sock,server_hostname=host,do_handshake_on_connect=False)
        sock.setblocking(False)
        while True:
            budget.check()
            try: sock.do_handshake(); return sock
            except ssl.SSLWantReadError: select.select([sock],[],[],.05)
            except ssl.SSLWantWriteError: select.select([],[sock],[],.05)
    except BaseException:
        sock.close(); raise
