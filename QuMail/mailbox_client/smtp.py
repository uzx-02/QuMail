"""Explicit Gmail development adapter. No endpoint override or password fallback."""
import socket
import ssl
import time
from core.crypto_envelope.model import Budget
from .connection import connect
from core.outbox.smtp_transport import SMTPSubmission, BoundedSMTP


class GmailConnection(BoundedSMTP):
    def _get_socket(self, host, port, timeout):
        if (host, port) != ('smtp.gmail.com', 587):
            raise ValueError('provider endpoint rejected')
        self.sock = connect(host,port,Budget(self.cancel,min(self.deadline,time.monotonic()+8)))
        self.arm()
        return self.sock


class GmailSMTP(SMTPSubmission):
    loopback_only = False
    client_type = GmailConnection

    def __init__(self, resolver):
        self.host, self.port = 'smtp.gmail.com', 587
        self.resolver = resolver
        self.context = ssl.create_default_context()
        self.context.minimum_version = ssl.TLSVersion.TLSv1_2
