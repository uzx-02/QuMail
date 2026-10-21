"""Controlled blocking operations in a real isolated worker; never a live provider."""
import os
from pathlib import Path
import runpy
import sys
import time

mode,marker=sys.argv[1:]
def block(*args,**kwargs):
    Path(marker).write_text(str(os.getpid()))
    time.sleep(60)
    raise OSError('controlled blocked operation')
if mode=='dns':
    import socket
    socket.getaddrinfo=block
elif mode=='oauth':
    import requests
    requests.Session.request=block
else: raise ValueError('fixture mode')
runpy.run_module('transport.network_worker',run_name='__main__')
