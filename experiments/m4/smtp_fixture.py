"""Test/development fixture only: disposable CA/server key and synthetic resolver."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from email.policy import SMTP
from pathlib import Path
import hashlib
import ipaddress
import socket
import ssl
import threading
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from .smtp_transport import MailCredential
from .model import Failure, Error


class SyntheticResolver:
    def __init__(self, context): self.context, self.calls = context, 0
    def resolve(self, handle, sender, cancel, deadline):
        if handle.context != self.context: raise Failure(Error.ACCOUNT)
        self.calls += 1
        return MailCredential(sender.value, 'disposable-fixture-not-a-real-token')


class SMTPFixtureBuilder:
    """Standard MIME container for SMTP byte qualification, NOT M5 protected mail."""
    def build(self, account, binding, plaintext, message_id):
        raw = account.seal_fixture(binding, plaintext)
        message = EmailMessage(policy=SMTP)
        message['From'] = account.sender.value
        message['To'] = ', '.join(a.value for a in binding.recipients)
        message['Message-ID'] = message_id
        message['Subject'] = 'M4 disposable protocol fixture'
        message.set_content(raw, maintype='application', subtype='octet-stream', cte='base64')
        return message.as_bytes()


def certificates(directory, mode='valid'):
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Disposable M4 fixture root')])
    ca = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(days=1))
        .not_valid_after(now+timedelta(days=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),True)
        .sign(ca_key,hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    host = '127.0.0.2' if mode == 'wrong-host' else '127.0.0.1'
    cert = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,host)]))
        .issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-timedelta(days=2)).not_valid_after(now-timedelta(days=1) if mode=='expired' else now+timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(host))]),False)
        .sign(ca_key,hashes.SHA256()))
    directory=Path(directory); directory.mkdir(parents=True,exist_ok=True)
    (directory/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    (directory/'cert.pem').write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (directory/'key.pem').write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
    server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); server.load_cert_chain(directory/'cert.pem',directory/'key.pem')
    client=ssl.create_default_context()
    if mode!='untrusted': client.load_verify_locations(cadata=ca.public_bytes(serialization.Encoding.PEM).decode())
    return server,client


class SMTPServer:
    """Small deterministic server; observations never contain AUTH values/body bytes."""
    def __init__(self, directory, mode='success', cert_mode='valid'):
        self.server_context,self.client_context=certificates(directory,cert_mode)
        self.mode=mode; self.events=[]; self.digests=[]; self.lengths=[]
        self.accepted=threading.Event(); self.paused=threading.Event(); self.release=threading.Event()
        self.done=threading.Event(); self.clients=[]
        self.listener=socket.socket(); self.listener.bind(('127.0.0.1',0)); self.listener.listen()
        self.listener.settimeout(.1); self.port=self.listener.getsockname()[1]
        self.thread=threading.Thread(target=self.run,daemon=True)

    def __enter__(self): self.thread.start(); return self
    def __exit__(self,*args):
        self.done.set(); self.release.set(); self.listener.close()
        for sock in self.clients:
            try: sock.shutdown(socket.SHUT_RDWR); sock.close()
            except OSError: pass
        self.thread.join(timeout=3)

    def run(self):
        while not self.done.is_set():
            try: sock,_=self.listener.accept()
            except socket.timeout: continue
            except OSError: return
            self.clients.append(sock)
            try: self.serve(sock)
            except (OSError,ValueError): pass
            finally:
                for client in self.clients:
                    try: client.close()
                    except OSError: pass

    def serve(self,sock):
        sock.settimeout(4); reader=sock.makefile('rb'); tls=False; recipients=0
        def send(data): sock.sendall(data)
        def pause(stage):
            if self.mode=='stall-'+stage:
                self.paused.set(); self.release.wait(4)
        try:
            pause('greeting'); send(b'220 fixture ESMTP\r\n')
            while not self.done.is_set():
                line=reader.readline(16385)
                if not line or len(line)>16384: return
                command=line.split(b' ',1)[0].strip().upper()
                self.events.append(command.decode('ascii',errors='replace')+('-TLS' if tls else '-CLEAR'))
                if command==b'EHLO':
                    pause('ehlo-tls' if tls else 'ehlo')
                    if self.mode=='oversized': send(b'250 '+b'x'*1100+b'\r\n'); return
                    send(b'250-fixture\r\n'+(b'250 AUTH XOAUTH2\r\n' if tls or self.mode=='missing-starttls' else b'250 STARTTLS\r\n'))
                elif command==b'STARTTLS':
                    if self.mode=='tls-reject': send(b'454 unavailable\r\n'); return
                    send(b'220 negotiate\r\n'); pause('tls'); reader.close()
                    sock=self.server_context.wrap_socket(sock,server_side=True)
                    self.clients.append(sock); reader=sock.makefile('rb'); tls=True
                elif command==b'AUTH': pause('auth'); send(b'535 rejected\r\n' if self.mode=='auth-reject' else b'235 authenticated\r\n')
                elif command==b'MAIL': pause('mail'); send(b'250 sender\r\n')
                elif command==b'RCPT':
                    recipients+=1; pause('rcpt')
                    send(b'550 rejected\r\n' if self.mode=='recipient-reject' or (self.mode=='second-recipient-reject' and recipients==2) else b'250 recipient\r\n')
                elif command==b'DATA':
                    pause('data')
                    if self.mode=='data-reject': send(b'554 rejected\r\n'); continue
                    send(b'354 continue\r\n')
                    if self.mode=='disconnect-data': return
                    payload=bytearray()
                    while True:
                        part=reader.readline(2048)
                        if not part: return
                        if part==b'.\r\n': break
                        if part.startswith(b'..'): part=part[1:]
                        payload.extend(part)
                        if len(payload)>2*1024*1024: return
                    self.digests.append(hashlib.sha256(payload).hexdigest()); self.lengths.append(len(payload))
                    self.accepted.set(); pause('final')
                    if self.mode=='final-loss': return
                    send(b'554 body rejected\r\n' if self.mode=='final-reject' else b'250 queued\r\n')
                    if self.mode=='close-after-accept': return
                elif command==b'QUIT': return
                else: send(b'500 unsupported\r\n')
        finally: reader.close()
