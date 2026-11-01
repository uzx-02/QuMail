"""Fresh one-day relay CA and endpoint credentials in pytest disposable storage."""
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import ssl
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


def contexts(directory, peers):
    directory.mkdir()
    now = datetime.now(timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'Disposable relay-only CA')])
    def base(subject,key):
        return (x509.CertificateBuilder().subject_name(subject).issuer_name(name).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
                .not_valid_after(now+timedelta(days=1)))
    ca = base(name,ca_key).add_extension(x509.BasicConstraints(ca=True,path_length=0),True).sign(ca_key,hashes.SHA256())
    ca_pem = ca.public_bytes(serialization.Encoding.PEM).decode()
    def issue(label,server=False):
        key = rsa.generate_private_key(public_exponent=65537,key_size=2048)
        builder = base(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,label)]),key)
        builder = builder.add_extension(x509.BasicConstraints(ca=False,path_length=None),True)
        builder = builder.add_extension(x509.ExtendedKeyUsage([
            ExtendedKeyUsageOID.SERVER_AUTH if server else ExtendedKeyUsageOID.CLIENT_AUTH]),True)
        if server:
            builder = builder.add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),False)
        cert = builder.sign(ca_key,hashes.SHA256())
        cp,kp = directory/(label+'.pem'),directory/(label+'.key')
        cp.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        kp.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        return cp,kp,hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    cp,kp,_ = issue('server',True)
    server = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server.minimum_version = ssl.TLSVersion.TLSv1_2
    server.load_cert_chain(cp,kp); server.load_verify_locations(cadata=ca_pem); server.verify_mode=ssl.CERT_REQUIRED
    clients,registry = [],{}
    for i,peer in enumerate(peers):
        cp,kp,digest = issue('endpoint'+str(i))
        client = ssl.create_default_context(cadata=ca_pem); client.load_cert_chain(cp,kp)
        clients.append(client); registry[digest]=peer
    anonymous = ssl.create_default_context(cadata=ca_pem)
    return server,clients,registry,anonymous
