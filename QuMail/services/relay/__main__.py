"""Explicit local-only operator entry point. No credential discovery or provisioning."""
import argparse
import json
from pathlib import Path
import ssl

from .http import Server, unique
from .store import Store, Peer


def main():
    parser=argparse.ArgumentParser(description='Development ciphertext relay; loopback only; no cloud qualification')
    parser.add_argument('--database',required=True)
    parser.add_argument('--create',action='store_true',help='create NEW local database, then exit')
    parser.add_argument('--server-cert')
    parser.add_argument('--server-key')
    parser.add_argument('--relay-client-ca')
    parser.add_argument('--registry',help='public JSON: certificate SHA256 -> {principal,device}')
    parser.add_argument('--port',type=int,default=8443)
    args=parser.parse_args()
    if args.create:
        Store.create(args.database); print('New local relay database created.'); return
    if not all((args.server_cert,args.server_key,args.relay_client_ca,args.registry)):
        parser.error('explicit server TLS files, dedicated relay-client CA and registry are required')
    with Path(args.registry).open('rb') as file: raw=file.read(65537)
    if len(raw)>65536: parser.error('registry exceeds limit')
    values=json.loads(raw,object_pairs_hook=unique)
    if not isinstance(values,dict) or len(values)>256: parser.error('registry exceeds limit')
    peers={digest:Peer(**value) for digest,value in values.items()}
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version=ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(args.server_cert,args.server_key)
    context.load_verify_locations(cafile=args.relay_client_ca)
    context.verify_mode=ssl.CERT_REQUIRED
    with Server(Store(args.database),context,peers,port=args.port) as server:
        print(f'Local-only relay listening on 127.0.0.1:{server.server_port}; stop with Ctrl+C.')
        try: server.thread.join()
        except KeyboardInterrupt: pass


if __name__=='__main__': main()
