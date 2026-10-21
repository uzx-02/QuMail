"""Disposable TLS IMAP server. Synthetic identities; no Gmail/live acceptance claim."""
import base64
import socket
import threading
from experiments.m4.smtp_fixture import certificates
from mailbox_client.gmail import LimitedIMAP


class Server:
    def __init__(self, path, messages, cert_mode='valid'):
        self.server_context, self.client_context = certificates(path, cert_mode)
        self.messages = messages
        self.validity = 17
        self.events = []
        self.pause = False
        self.paused = threading.Event(); self.release = threading.Event()
        self.stop = threading.Event(); self.clients = []
        self.socket = socket.socket(); self.socket.bind(('127.0.0.1', 0)); self.socket.listen()
        self.socket.settimeout(.1); self.port = self.socket.getsockname()[1]
        self.thread = threading.Thread(target=self.run)

    def factory(self, host, port, *, ssl_context, timeout, budget=None):
        assert host == 'imap.gmail.com' and port == 993
        assert ssl_context.check_hostname
        return LimitedIMAP('127.0.0.1', self.port, ssl_context=self.client_context, timeout=timeout,budget=budget)

    def run(self):
        while not self.stop.is_set():
            try: raw, _ = self.socket.accept()
            except socket.timeout: continue
            except OSError: break
            try:
                with self.server_context.wrap_socket(raw, server_side=True) as connection:
                    self.clients.append(connection); connection.settimeout(4)
                    self.serve(connection)
            except (OSError, ValueError): raw.close()

    def serve(self, connection):
        reader = connection.makefile('rb'); messages = {}; readonly = True
        def send(raw): connection.sendall(raw)
        send(b'* OK disposable IMAP fixture\r\n')
        try:
            while not self.stop.is_set():
                line = reader.readline(8192)
                if not line: return
                tag, command, *tail = line.rstrip(b'\r\n').split(b' ', 2)
                args = tail[0] if tail else b''
                self.events.append(command.decode())  # Never record AUTH bytes/body.
                if command == b'CAPABILITY': send(b'* CAPABILITY IMAP4rev1 AUTH=XOAUTH2\r\n')
                elif command == b'AUTHENTICATE':
                    send(b'+ \r\n')
                    decoded = base64.b64decode(reader.readline().strip())
                    if b'auth=Bearer synthetic-mail-token\x01' not in decoded:
                        send(tag+b' NO auth rejected\r\n'); continue
                    address = decoded.split(b'\x01')[0][5:].decode()
                    messages = self.messages.get(address, {})
                elif command in (b'EXAMINE', b'SELECT'):
                    readonly = command == b'EXAMINE'
                    send(f'* {len(messages)} EXISTS\r\n* OK [UIDVALIDITY {self.validity}] valid\r\n* OK [UIDNEXT {max(messages,default=0)+1}] next\r\n'.encode())
                elif command == b'UID':
                    action, _, values = args.partition(b' ')
                    self.events.append(action.decode())
                    if action == b'SEARCH':
                        start, end = map(int, values.split()[-1].split(b':'))
                        send(b'* SEARCH '+b' '.join(str(uid).encode() for uid in messages if start <= uid <= end)+b'\r\n')
                    elif action == b'STORE':
                        assert not readonly
                        uid = int(values.split()[0])
                        if uid in messages: messages[uid]['seen'] = b'+FLAGS' in values
                    elif action == b'FETCH':
                        if self.pause:
                            self.paused.set(); self.release.wait(4)
                        uid = int(values.split()[0])
                        if uid in messages:
                            item = messages[uid]; raw = item['raw']
                            if b'BODY[' in values: item['seen'] = True
                            flags = b'\\Seen' if item['seen'] else b''
                            if b'BODY.PEEK' not in values:
                                send(b'* 1 FETCH (UID '+str(uid).encode()+b' FLAGS ('+flags+b'))\r\n')
                            else:
                                section = b'HEADER.FIELDS (FROM SUBJECT DATE CONTENT-TYPE)' if b'HEADER.FIELDS' in values else b''
                                payload = raw.partition(b'\r\n\r\n')[0]+b'\r\n\r\n' if section else raw
                                prefix = b'* 1 FETCH (UID '+str(uid).encode()+b' FLAGS ('+flags+b') RFC822.SIZE '+str(len(raw)).encode()
                                send(prefix+b' BODY['+section+b'] {'+str(len(payload)).encode()+b'}\r\n'+payload+b')\r\n')
                else:
                    send(tag+b' BAD unsupported\r\n'); continue
                send(tag+b' OK completed\r\n')
        finally: reader.close()

    def __enter__(self): self.thread.start(); return self

    def __exit__(self, *args):
        self.stop.set(); self.release.set(); self.socket.close()
        for client in self.clients:
            try: client.shutdown(socket.SHUT_RDWR)
            except OSError: pass
        self.thread.join(5)
        assert not self.thread.is_alive()
