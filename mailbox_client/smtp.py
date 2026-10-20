"""Explicit Gmail development adapter. No endpoint override or password fallback."""
import socket
import ssl
from experiments.m4.smtp_transport import SMTPSubmission, BoundedSMTP


class GmailConnection(BoundedSMTP):
    def _get_socket(self, host, port, timeout):
        if (host, port) != ('smtp.gmail.com', 587):
            raise ValueError('provider endpoint rejected')
        # DNS/connect remains a bounded-socket library phase, not a claim of
        # sub-second DNS cancellation. UI publication is independently cancelled.
        self.sock = socket.create_connection((host, port), timeout=min(8, self.arm()))
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
