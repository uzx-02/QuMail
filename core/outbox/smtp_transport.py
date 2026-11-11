"""Controlled loopback SMTP/STARTTLS qualification; no external destinations."""
import base64
import ipaddress
import re
import select
import smtplib
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from .model import Outcome, Failure, Error, MAX_ENVELOPE


@dataclass(frozen=True, repr=False)
class MailCredential:
    address: str
    token: str


class VaultMailCredentials:
    """No caches, no refresh/password fallback; Google identity scopes are insufficient."""
    def __init__(self, vault): self.vault = vault

    def resolve(self, handle, sender, cancel, deadline):
        if cancel.is_set() or time.monotonic() >= deadline: raise Failure(Error.CANCELLED)
        data = self.vault._read(handle.context)
        self.vault.check(data, handle.context, active=True)
        token = data.get('oauth', {})
        if (data['address'] != sender.value or handle.context.issuer != 'https://accounts.google.com' or
            'https://mail.google.com/' not in token.get('scopes', []) or
            token.get('expiry', 0) <= time.time() or not token.get('access_token')):
            raise Failure(Error.CREDENTIAL)
        return MailCredential(sender.value, token['access_token'])


class BoundedSMTP(smtplib.SMTP):
    def __init__(self, cancel, deadline):
        self.cancel, self.deadline = cancel, deadline
        self.incoming = bytearray()
        super().__init__(local_hostname='qumail-fixture.invalid', timeout=1)

    def arm(self):
        remaining = self.deadline-time.monotonic()
        if self.cancel.is_set() or remaining <= 0: raise TimeoutError('operation stopped')
        if self.sock: self.sock.settimeout(remaining)
        return remaining

    def _get_socket(self, host, port, timeout):
        # Numeric IPv4 loopback only: no DNS/rebinding or external routing.
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.arm(); self.sock.connect((host, port))
        return self.sock

    def send(self, data):
        if isinstance(data,str): data=data.encode('ascii')
        pending=memoryview(data)
        while pending:
            self.sock.settimeout(min(.1,self.arm()))
            try: count=self.sock.send(pending[:16384])
            except socket.timeout: continue
            if not count: raise smtplib.SMTPServerDisconnected('closed')
            pending=pending[count:]

    def getreply(self):
        self.arm()
        lines = []; total = 0; expected = None
        for _ in range(32):
            while b'\n' not in self.incoming:
                if len(self.incoming)>1024: raise smtplib.SMTPServerDisconnected('reply limit')
                self.sock.settimeout(min(.1,self.arm()))
                try: chunk=self.sock.recv(1024)
                except socket.timeout: continue
                if not chunk: raise smtplib.SMTPServerDisconnected('closed')
                self.incoming.extend(chunk)
            end=self.incoming.index(b'\n')+1
            line=bytes(self.incoming[:end]); del self.incoming[:end]
            total += len(line)
            if not line or len(line) > 1024 or total > 32768 or not re.match(rb'^\d{3}[ -].*\r\n$', line):
                raise smtplib.SMTPServerDisconnected('invalid bounded reply')
            code = int(line[:3])
            if expected is not None and code != expected: raise smtplib.SMTPServerDisconnected('reply mismatch')
            expected = code; lines.append(line[4:-2])
            if line[3:4] == b' ': return code, b'\n'.join(lines)
        raise smtplib.SMTPServerDisconnected('reply limit')

    def verified_starttls(self, context):
        if not self.has_extn('starttls'): raise smtplib.SMTPNotSupportedError('STARTTLS required')
        if self.docmd('STARTTLS')[0] != 220: raise smtplib.SMTPException('TLS rejected')
        self.arm()
        if self.file: self.file.close(); self.file = None
        if self.incoming: raise smtplib.SMTPException('unexpected pre-TLS bytes')
        # Assign before handshake so cancellation can shutdown the actual SSL socket.
        self.sock = context.wrap_socket(self.sock, server_hostname=self._host, do_handshake_on_connect=False)
        # A blocking SSL handshake is not reliably interrupted by another thread's
        # shutdown on Windows. Poll readiness and cancellation on the owner thread.
        while True:
            remaining = self.arm()
            self.sock.setblocking(False)
            try:
                self.sock.do_handshake()
                break
            except ssl.SSLWantReadError:
                select.select([self.sock], [], [], min(.1, remaining))
            except ssl.SSLWantWriteError:
                select.select([], [self.sock], [], min(.1, remaining))
        self.arm()
        self.helo_resp = self.ehlo_resp = None
        self.esmtp_features = {}; self.does_esmtp = False


class SMTPSubmission:
    """Shared bounded protocol; endpoint policy belongs to concrete adapters."""
    simulation_only = False
    client_type = BoundedSMTP

    def submit(self, envelope, credential, cancel, deadline):
        if credential.context != envelope.account: return Outcome.REJECTED
        if self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname: return Outcome.REJECTED
        if any(c in address.value for address in (envelope.sender, *envelope.binding.recipients) for c in '\r\n\x00\x01'):
            return Outcome.REJECTED
        raw = envelope.serialized
        # SMTP DATA is CRLF line-oriented; reject instead of silently rewriting
        # persisted bytes. Binary OpenPGP must use the explicit fixture builder.
        if (not raw or len(raw) > MAX_ENVELOPE or not raw.endswith(b'\r\n') or
            b'\x00' in raw or b'\n' in raw.replace(b'\r\n', b'') or b'\r' in raw.replace(b'\r\n', b'') or
            any(len(line) > 998 for line in raw.split(b'\r\n')) or not raw.isascii()): return Outcome.REJECTED
        smtp = self.client_type(cancel, deadline)
        stopped = threading.Event(); possible = False
        def interrupt():
            while not stopped.wait(.02):
                if cancel.is_set() or time.monotonic() >= deadline:
                    sock = smtp.sock
                    if sock:
                        try: sock.shutdown(socket.SHUT_RDWR)
                        except OSError: pass
                    return
        watchdog = threading.Thread(target=interrupt, daemon=True); watchdog.start()
        try:
            smtp._host = self.host
            if smtp.connect(self.host, self.port)[0] != 220: return Outcome.REJECTED
            if smtp.ehlo()[0] != 250: return Outcome.REJECTED
            smtp.verified_starttls(self.context)
            if smtp.ehlo()[0] != 250: return Outcome.REJECTED
            if 'XOAUTH2' not in smtp.esmtp_features.get('auth', '').upper().split(): return Outcome.REJECTED
            smtp.arm()
            resolved = self.resolver.resolve(credential, envelope.sender, cancel, deadline)
            if (resolved.address != envelope.sender.value or not resolved.token or len(resolved.token) > 8192 or
                any(c in resolved.token for c in '\x00\x01\r\n')): return Outcome.REJECTED
            auth = base64.b64encode(f'user={resolved.address}\x01auth=Bearer {resolved.token}\x01\x01'.encode()).decode()
            auth_code = smtp.docmd('AUTH', 'XOAUTH2 '+auth)[0]
            if auth_code == 334:
                # Google requires an empty response to an OAuth error challenge.
                # Never log/decode its contents or retry with another credential.
                smtp.docmd('')
                return Outcome.REJECTED
            if auth_code != 235: return Outcome.REJECTED
            if smtp.mail(envelope.sender.value)[0] != 250: return Outcome.REJECTED
            for recipient in envelope.binding.recipients:
                if smtp.rcpt(recipient.value)[0] not in (250, 251): return Outcome.REJECTED
            if smtp.docmd('DATA')[0] != 354: return Outcome.REJECTED
            smtp.arm()
            framed = re.sub(rb'(?m)^\.', b'..', raw) + b'.\r\n'
            possible = True  # Any failure from here conservatively admits acceptance.
            smtp.send(framed)
            code, _ = smtp.getreply()
            if 200 <= code < 300: return Outcome.ACCEPTED
            if 400 <= code < 600: return Outcome.REJECTED
            return Outcome.UNKNOWN
        except Exception:
            return Outcome.UNKNOWN if possible else Outcome.REJECTED
        finally:
            # No QUIT is needed to establish acceptance. Cleanup must never replace it.
            stopped.set()
            try: smtp.close()
            except Exception: pass
            watchdog.join(timeout=1)


class LoopbackSMTP(SMTPSubmission):
    loopback_only = True

    def __init__(self, host, port, resolver, *, fixture_context=None):
        address = ipaddress.ip_address(host)
        if address.version != 4 or not address.is_loopback or not 0 < port < 65536:
            raise Failure(Error.TRANSPORT)
        self.host, self.port, self.resolver = host, port, resolver
        self.context = fixture_context or ssl.create_default_context()
        if self.context.verify_mode != ssl.CERT_REQUIRED or not self.context.check_hostname:
            raise Failure(Error.TRANSPORT)
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
