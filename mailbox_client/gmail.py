"""Gmail IMAP TLS/XOAUTH2. UID-only identity, EXAMINE + PEEK for every read.

Only explicit set_seen uses a writable selection. No CLOSE/EXPUNGE, raw diagnostics,
credential cache discovery, sample data, server-specified endpoints or TLS bypass.
"""
from contextlib import contextmanager
from email.parser import BytesHeaderParser
from email.policy import default
import imaplib
import re
import select
import ssl
import time
import threading
from experiments.m5.model import Budget
from .connection import connect,secure
from .model import *

HOST = 'imap.gmail.com'
MAIL_SCOPE = 'https://mail.google.com/'


class LimitedIMAP(imaplib.IMAP4_SSL):
    def __init__(self, host, port, *, ssl_context, timeout, budget=None):
        self.remaining = 1024 * 1024
        self.literal_limit = MAX_WIRE
        self.budget = budget or Budget(threading.Event(),time.monotonic()+timeout)
        self.buffer = bytearray()
        try: super().__init__(host, port, ssl_context=ssl_context, timeout=timeout)
        except BaseException:
            if getattr(self,'sock',None): self.sock.close()
            raise
        self.debug = 0

    def _create_socket(self,timeout):
        return secure(connect(self.host,self.port,self.budget),self.ssl_context,self.host,self.budget)

    def set_budget(self, budget):
        self.budget = budget
        self.sock.setblocking(False)

    def receive(self):
        while True:
            self.budget.check()
            try:
                data = self.sock.recv(16384)
                if not data: raise self.abort('connection ended')
                self.buffer.extend(data)
                return
            except ssl.SSLWantReadError: select.select([self.sock], [], [], .05)
            except ssl.SSLWantWriteError: select.select([], [self.sock], [], .05)

    def send(self, data):
        if self.budget is None: return super().send(data)
        pending = memoryview(data)
        while pending:
            self.budget.check()
            try:
                count = self.sock.send(pending)
                if not count: raise self.abort('connection ended')
                pending = pending[count:]
            except ssl.SSLWantReadError: select.select([self.sock], [], [], .05)
            except ssl.SSLWantWriteError: select.select([], [self.sock], [], .05)

    def read(self, size):
        if size > self.literal_limit or size > self.remaining:
            raise Failure(Code.LIMIT)  # Reject literal length before allocation.
        self.remaining -= size
        if self.budget is None: return super().read(size)
        while len(self.buffer) < size: self.receive()
        result = bytes(self.buffer[:size]); del self.buffer[:size]
        return result

    def readline(self):
        if self.budget is None:
            line = self.file.readline(min(16385, self.remaining + 1))
        else:
            while b'\n' not in self.buffer:
                if len(self.buffer) > 16384: raise Failure(Code.LIMIT)
                self.receive()
            end = self.buffer.index(b'\n')+1
            line = bytes(self.buffer[:end]); del self.buffer[:end]
        self.remaining -= len(line)
        if self.remaining < 0 or len(line) > 16384:
            raise Failure(Code.LIMIT)
        return line


def ok(reply):
    status, data = reply
    if status != 'OK':
        raise Failure(Code.PROTOCOL)
    return data


def number(connection, name):
    kind, values = connection.response(name)
    if kind != name or len(values or []) != 1 or not re.fullmatch(rb'[0-9]{1,10}', values[0] or b''):
        raise Failure(Code.PROTOCOL)
    value = int(values[0])
    if not 0 < value < 2**32:
        raise Failure(Code.PROTOCOL)
    return value


def field(header, name):
    if len(header.get_all(name, [])) > 1:
        return '[ambiguous transport header]'
    # Plain text only, no bidi/control characters in list labels.
    value = str(header.get(name, ''))
    return ''.join(c if c.isprintable() and c not in '\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069' else ' ' for c in value)[:512]


def fetched(data, expected, body):
    literals = [v for v in data if isinstance(v, tuple)]
    if len(literals) != 1:
        raise Failure(Code.MISSING if not literals else Code.PROTOCOL)
    meta, raw = literals[0]
    uids = re.findall(rb'\bUID ([0-9]+)', meta)
    sizes = re.findall(rb'\bRFC822.SIZE ([0-9]+)', meta)
    flags = re.findall(rb'\bFLAGS \(([^)]*)\)', meta)
    if len(uids) != 1 or int(uids[0]) != expected or len(sizes) != 1 or len(flags) != 1:
        raise Failure(Code.PROTOCOL)
    size = int(sizes[0])
    if len(raw) > (MAX_WIRE if body else MAX_HEADER):
        raise Failure(Code.LIMIT)
    if body and (size > MAX_WIRE or len(raw) != size):
        raise Failure(Code.LIMIT if size > MAX_WIRE else Code.PROTOCOL)
    return raw, size, b'\\Seen' in flags[0].split()


class GmailMailbox:
    def __init__(self, factory=LimitedIMAP):
        self.factory = factory  # Explicit test seam; application never configures a fixture.

    @contextmanager
    def connection(self, credential, budget, write=False):
        connection = None
        try:
            budget.check()
            if credential.context.issuer != 'https://accounts.google.com' or any(c in credential.address + credential.token for c in '\r\n\x00\x01'):
                raise Failure(Code.AUTH)
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            # DNS, connect, handshake and greeting share one cancellable setup budget.
            setup=Budget(budget.cancel,min(budget.deadline,time.monotonic()+8))
            connection = self.factory(HOST, 993, ssl_context=context,
                                      timeout=8,budget=setup)
            connection.set_budget(budget)
            budget.check()
            def challenge(value):
                if value: return b''  # Gmail error challenge must receive an empty response.
                return ('user='+credential.address+'\x01auth=Bearer '+credential.token+'\x01\x01').encode()
            ok(connection.authenticate('XOAUTH2', challenge))
            ok(connection.select('INBOX', readonly=not write))
            uidvalidity = number(connection, 'UIDVALIDITY')
            budget.check()
            yield connection, uidvalidity
            budget.check()
        except Failure:
            raise
        except Exception:
            if budget.cancel.is_set() or time.monotonic() >= budget.deadline:
                raise Failure(Code.CANCELLED) from None
            raise Failure(Code.TRANSPORT) from None
        finally:
            if connection:
                # Shutdown, not CLOSE (which may expunge). Never let logout delay cancellation.
                try: connection.shutdown()
                except Exception: pass

    def headers(self, credential, budget, before=None):
        with self.connection(credential, budget) as (connection, validity):
            if before is not None and (type(before) is not tuple or len(before) != 2 or before[0] != validity):
                raise Failure(Code.STALE)
            end = number(connection, 'UIDNEXT') - 1
            if before is not None:
                if type(before[1]) is not int or before[1] < 1: raise Failure(Code.PROTOCOL)
                end = min(end, before[1]-1)
            if end < 1: return Page(validity, (), None)
            # Bounded UID window, not an unbounded SEARCH ALL. Sparse pages may be empty.
            start = max(1, end-199)
            data = ok(connection.uid('SEARCH', None, 'UID', f'{start}:{end}'))
            tokens = b' '.join(v for v in data if isinstance(v, bytes)).split()
            if len(tokens) > 200 or any(not re.fullmatch(rb'[0-9]{1,10}', v) for v in tokens):
                raise Failure(Code.PROTOCOL)
            uids = sorted(set(map(int, tokens)), reverse=True)
            if any(not start <= uid <= end for uid in uids): raise Failure(Code.PROTOCOL)
            selected = uids[:PAGE_SIZE]
            connection.literal_limit = MAX_HEADER
            rows = []
            for uid in selected:
                budget.check()
                data = ok(connection.uid('FETCH', str(uid), '(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE CONTENT-TYPE)])'))
                raw, size, seen = fetched(data, uid, False)
                header = BytesHeaderParser(policy=default).parsebytes(raw)
                rows.append(Header(MessageKey(credential.context, 'INBOX', validity, uid),
                                   field(header, 'From'), field(header, 'Subject'), field(header, 'Date'), size, seen))
            next_uid = selected[-1] if len(uids) > PAGE_SIZE else start
            return Page(validity, tuple(rows), next_uid if next_uid > 1 else None)

    def fetch(self, credential, key, budget):
        if key.account != credential.context: raise Failure(Code.STALE)
        with self.connection(credential, budget) as (connection, validity):
            if validity != key.uidvalidity: raise Failure(Code.STALE)
            raw, _, seen = fetched(ok(connection.uid('FETCH', str(key.uid), '(UID FLAGS RFC822.SIZE BODY.PEEK[])')), key.uid, True)
            return raw, seen

    def set_seen(self, credential, key, seen, budget):
        if key.account != credential.context or type(seen) is not bool: raise Failure(Code.STALE)
        with self.connection(credential, budget, write=True) as (connection, validity):
            if validity != key.uidvalidity: raise Failure(Code.STALE)
            ok(connection.uid('STORE', str(key.uid), '+FLAGS.SILENT' if seen else '-FLAGS.SILENT', '(\\Seen)'))
            # Missing UID can return OK; confirm the actual flag instead of claiming success.
            data = ok(connection.uid('FETCH', str(key.uid), '(UID FLAGS)'))
            rows = [v for v in data if isinstance(v, bytes)]
            matches = [v for v in rows if re.search(rb'\bUID '+str(key.uid).encode()+rb'\b', v)]
            if len(matches) != 1: raise Failure(Code.MISSING)
            flags = re.findall(rb'FLAGS \(([^)]*)\)', matches[0])
            if len(flags) != 1 or (b'\\Seen' in flags[0].split()) != seen: raise Failure(Code.PROTOCOL)
            return seen
