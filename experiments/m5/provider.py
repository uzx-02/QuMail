"""Cancelled/bounded private IPC; M3 identity provider stays unchanged."""
import json
import subprocess
import threading
from pathlib import Path
from experiments.m3.vault import PROFILE
from .model import Failure, Code, Budget

MAX_PIPE=8*1024*1024


class Provider:
    def __init__(self, executable): self.executable=Path(executable).resolve(strict=True)

    def call(self, op, budget: Budget, **values):
        budget.check()
        def encode(value):
            if isinstance(value,bytes): return list(value)
            if isinstance(value,(tuple,list)): return [encode(v) for v in value]
            return value
        request=json.dumps(dict(version=1,op=op,profile=PROFILE,**{k:encode(v) for k,v in values.items()}),separators=(',',':')).encode()
        if len(request)>MAX_PIPE: raise Failure(Code.LIMIT)
        try:
            p=subprocess.Popen([str(self.executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError: raise Failure(Code.PROVIDER) from None
        output=bytearray(); overflow=threading.Event()
        def read():
            while True:
                chunk=p.stdout.read(65536)
                if not chunk: break
                if len(output)+len(chunk)>MAX_PIPE: overflow.set(); p.kill(); break
                output.extend(chunk)
        def write():
            try: p.stdin.write(request); p.stdin.close()
            except (BrokenPipeError,OSError): pass
        reader=threading.Thread(target=read); writer=threading.Thread(target=write)
        reader.start(); writer.start()
        try:
            while p.poll() is None:
                budget.check()
                try: p.wait(timeout=.05)
                except subprocess.TimeoutExpired: pass
            budget.check()
        finally:
            if p.poll() is None: p.kill()
            p.wait(); reader.join(); writer.join(); p.stdin.close(); p.stdout.close()
        if overflow.is_set(): raise Failure(Code.LIMIT)
        if p.returncode: raise Failure(Code.PROVIDER)
        try:
            response=json.loads(output)
            if response.get('ok') is not True or not isinstance(response.get('value'),dict): raise ValueError()
            result=response['value']
            if op in ('seal','peer_seal','open','peer_open'):
                data=result['data']
                if not isinstance(data,list) or any(type(x) is not int or not 0<=x<=255 for x in data): raise ValueError()
                result['data']=bytes(data)
            elif op!='inspect': raise ValueError()  # Only the unchanged M3 public inspection IPC is reused.
            return result
        except (ValueError,TypeError,KeyError): raise Failure(Code.PROVIDER) from None
