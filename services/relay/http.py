"""Bounded loopback HTTPS/mTLS adapter; no public deployment in this lane.

The dedicated CA and exact certificate allowlist are the relay audience. Google
tokens, HTTP Authorization headers and certificate subject strings grant nothing.
Operator enrollment/revocation and distributed cloud storage remain separate gates.
"""
import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import socket
import ssl
import threading
from types import MappingProxyType

from .store import Code, Failure, MAX_WIRE

MAX_BODY = (MAX_WIRE * 4 // 3) + 4096
MAX_HEADERS = 8192


class HeaderReader:
    def __init__(self, reader): self.reader, self.remaining = reader, MAX_HEADERS
    def readline(self, size=-1):
        line = self.reader.readline(min(self.remaining+1, size) if size>=0 else self.remaining+1)
        self.remaining -= len(line)
        if self.remaining<0: raise Failure(Code.LIMIT)
        return line
    def read(self, size): return self.reader.read(size)
    def close(self): self.reader.close()


def unique(pairs):
    result = {}
    for key,value in pairs:
        if key in result: raise Failure(Code.INVALID)
        result[key] = value
    return result


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'  # Exactly one request per bounded connection.
    server_version = 'QuMail-relay-development'
    sys_version = ''
    def log_message(self, *_): pass  # No URLs, request IDs, bodies or credentials.
    def setup(self):
        super().setup()
        self.rfile = HeaderReader(self.rfile)
    def handle(self):
        try: super().handle()
        except (Failure, OSError, ValueError): pass
    def send_error(self, code, message=None, explain=None):
        self.respond(code, dict(error='invalid_http_request'))
    def respond(self, status, result):
        body = json.dumps(result, separators=(',',':')).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store')
        self.send_header('Connection','close')
        self.end_headers(); self.wfile.write(body)
    def do_POST(self):
        try:
            fingerprint = hashlib.sha256(self.connection.getpeercert(binary_form=True)).hexdigest()
            peer = self.server.peers.get(fingerprint)
            if peer is None: raise Failure(Code.DENIED)
            if (self.headers.get('Transfer-Encoding') or self.headers.get('Expect')
                    or self.headers.get('Authorization')
                    or self.headers.get('Content-Type')!='application/json'
                    or len(self.headers.get_all('Content-Length',[]))!=1):
                raise Failure(Code.INVALID)
            length = self.headers['Content-Length']
            if not re.fullmatch('[0-9]{1,7}',length): raise Failure(Code.INVALID)
            length = int(length)
            if not 0<length<=MAX_BODY: raise Failure(Code.LIMIT)
            body = self.rfile.read(length)
            if len(body)!=length: raise Failure(Code.INVALID)
            value = json.loads(body, object_pairs_hook=unique)
            if not isinstance(value,dict): raise Failure(Code.INVALID)
            store = self.server.store
            if self.path=='/v1/objects':
                if set(value)!={'key','recipient','ciphertext','ttl'}: raise Failure(Code.INVALID)
                if value['recipient'] not in {p.principal for p in self.server.peers.values()}:
                    raise Failure(Code.DENIED)
                payload = base64.b64decode(value['ciphertext'],validate=True)
                result = store.upload(peer,value['key'],value['recipient'],payload,value['ttl'])
            else:
                match = re.fullmatch('/v1/objects/([0-9a-f]{32})/(leases|download|ack)',self.path)
                if not match: raise Failure(Code.INVALID)
                object_id,action = match.groups()
                field = 'key' if action=='leases' else 'lease'
                if set(value)!={field}: raise Failure(Code.INVALID)
                if action=='leases': result = store.lease(peer,object_id,value[field])
                elif action=='download':
                    payload = store.download(peer,object_id,value[field])
                    result = dict(ciphertext=base64.b64encode(payload).decode())
                else: result = store.acknowledge(peer,object_id,value[field])
            self.respond(200,result)
        except Failure as error:
            status = {Code.INVALID:400,Code.DENIED:403,Code.CONFLICT:409,Code.LIMIT:429,Code.BACKEND:503}[error.code]
            self.respond(status,dict(error=error.code.value))
        except (ValueError,TypeError,RecursionError):
            self.respond(400,dict(error=Code.INVALID.value))


class Server(ThreadingHTTPServer):
    daemon_threads = False
    block_on_close = True
    request_queue_size = 16
    def __init__(self, store, context, peers, *, port=0):
        if context.verify_mode!=ssl.CERT_REQUIRED: raise Failure(Code.INVALID)
        self.store, self.context = store, context
        self.peers = MappingProxyType(dict(peers))
        if not self.peers or any(not re.fullmatch('[0-9a-f]{64}',key) for key in self.peers):
            raise Failure(Code.INVALID)
        self.slots = threading.BoundedSemaphore(16)
        self.stop = threading.Event()
        super().__init__(('127.0.0.1',port),Handler)
    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request); return
        try: super().process_request(request,address)
        except BaseException:
            self.slots.release(); raise
    def process_request_thread(self, request, address):
        wrapped = None
        timer = None
        try:
            request.settimeout(5)
            wrapped = self.context.wrap_socket(request,server_side=True,do_handshake_on_connect=False)
            def abort():
                try: wrapped.shutdown(socket.SHUT_RDWR)
                except OSError: pass
            timer = threading.Timer(5,abort)  # Overall, not just per-read timeout.
            timer.daemon = True; timer.start()
            wrapped.do_handshake()
            self.finish_request(wrapped,address)
        except (OSError,Failure): pass
        finally:
            if timer: timer.cancel(); timer.join()
            if wrapped: self.shutdown_request(wrapped)
            else: self.shutdown_request(request)
            self.slots.release()
    def __enter__(self):
        self.thread = threading.Thread(target=self.serve_forever,daemon=True)
        self.thread.start()
        def sweep():
            while not self.stop.wait(1):
                try: self.store.sweep()
                except Failure: pass  # Requests still return 503; never memory fallback.
        self.sweeper = threading.Thread(target=sweep,daemon=True)
        self.sweeper.start()
        return self
    def __exit__(self,*_):
        self.stop.set(); self.shutdown(); self.server_close()
        self.thread.join(); self.sweeper.join()
