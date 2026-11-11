"""Provisional helper IPC. Secret bytes never appear in argv or forwarded stderr."""
import json
from pathlib import Path
import subprocess
import threading
from .types import BoundaryError, Code

MAX_PIPE=8*1024*1024


class Provider:
    def __init__(self, executable: Path):
        self.executable=executable.resolve(strict=True)

    def call(self, op, **values):
        request=json.dumps(dict(version=1,op=op,**{
            k:list(v) if isinstance(v,bytes) else v for k,v in values.items()}),separators=(',',':')).encode()
        if len(request)>MAX_PIPE:
            raise BoundaryError(Code.LIMIT)
        try:
            process=subprocess.Popen([str(self.executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except OSError:
            raise BoundaryError(Code.PROVIDER) from None
        output=bytearray()
        exceeded=[]
        def read():
            while True:
                chunk=process.stdout.read(65536)
                if not chunk: break
                if len(output)+len(chunk)>MAX_PIPE:
                    exceeded.append(True); process.kill(); break
                output.extend(chunk)
        def write():
            try:
                process.stdin.write(request)
                process.stdin.close()
            except (BrokenPipeError,OSError): pass
        reader=threading.Thread(target=read,daemon=True)
        writer=threading.Thread(target=write,daemon=True)
        reader.start(); writer.start()
        try:
            process.wait(timeout=30)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
            raise BoundaryError(Code.PROVIDER) from None
        finally:
            reader.join(); writer.join()
            process.stdout.close()
            process.stdin.close()
        if exceeded: raise BoundaryError(Code.LIMIT)
        if process.returncode: raise BoundaryError(Code.PROVIDER)
        try:
            response=json.loads(output)
            if response.get('ok') is not True or not isinstance(response.get('value'),dict):
                raise ValueError()
            return response['value']
        except (ValueError,TypeError):
            raise BoundaryError(Code.PROVIDER) from None
