"""Private, bounded subprocess IPC for OS DNS and provider authorization waits."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

LIMIT=1024*1024


def call(request,cancel,deadline,*,command=None):
    def check():
        if cancel.is_set() or time.monotonic()>=deadline: raise TimeoutError('operation stopped')
    check()
    raw=json.dumps(request,separators=(',',':')).encode()
    if len(raw)>LIMIT: raise ValueError('request limit')
    process=subprocess.Popen(command or [sys.executable,'-m','transport.network_worker'],
        cwd=Path(__file__).resolve().parents[1],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    output=bytearray(); overflow=threading.Event()
    def read():
        while True:
            chunk=process.stdout.read(65536)
            if not chunk: return
            if len(output)+len(chunk)>LIMIT:
                overflow.set(); process.kill(); return
            output.extend(chunk)
    def write():
        try: process.stdin.write(raw); process.stdin.close()
        except (OSError,ValueError): pass
    reader=threading.Thread(target=read,name='qumail-private-reader')
    writer=threading.Thread(target=write,name='qumail-private-writer')
    reader.start(); writer.start()
    try:
        while process.poll() is None:
            check()
            try: process.wait(timeout=.05)
            except subprocess.TimeoutExpired: pass
        check()
    finally:
        if process.poll() is None: process.kill()
        process.wait(); reader.join(); writer.join()
        process.stdin.close(); process.stdout.close()
    if overflow.is_set() or process.returncode: raise OSError('provider worker failed')
    result=json.loads(output)
    if result.get('ok') is not True:
        from core.vault.types import BoundaryError,Code
        try: code=Code(result.get('code'))
        except ValueError: raise OSError('provider worker failed') from None
        raise BoundaryError(code)
    return result['value']
