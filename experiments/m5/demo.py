"""Explicit disposable compose/open fixture. No external service or real credentials."""
import argparse
import json
from pathlib import Path
import tempfile
import time
from PyQt6.QtWidgets import QApplication
from core.account_session import DevelopmentSession,AccountView
from experiments.m3.provider import Provider as IdentityProvider
from experiments.m3.secure_store import WindowsCredentialStore
from experiments.m3.types import EmailAddress,UserId,VerifiedProviderIdentity
from experiments.m3.vault import Vault
from experiments.m4.model import AccountAccess
from experiments.m4.services import SubmitOutbox
from experiments.m4.smtp_fixture import SMTPServer,SyntheticResolver
from experiments.m4.smtp_transport import LoopbackSMTP
from .provider import Provider
from .services import Compose,OpenMessage
from .panel import ComposePanel


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loopback',action='store_true'); parser.add_argument('--smoke',action='store_true')
    parser.add_argument('--scenario',choices=['success','auth-reject','final-loss'],default='success')
    args=parser.parse_args()
    if not args.loopback: parser.error('--loopback is required')
    app=QApplication.instance() or QApplication([]); root=Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='m5-demo-',dir=root/'tmp') as directory:
        path=Path(directory); store=WindowsCredentialStore()
        v=Vault.create(path/'vault.sqlite',store,IdentityProvider(root/'tmp/m2/target/debug/qumail-m3-provider.exe'))
        panel=None
        try:
            accounts=[]
            for name in ('sender','recipient','second'):
                address=EmailAddress(name+'@example.invalid')
                identity=VerifiedProviderIdentity('https://accounts.google.com','m5-synthetic-'+name,(address,),int(time.time())+3600,'fixture only')
                accounts.append(v.enroll(identity,address,UserId.new()))
            for ctx,key in accounts:
                for peer,peerkey in accounts:
                    if ctx==peer: continue
                    address=EmailAddress(v._read(peer)['address'])
                    fingerprint=v.import_contact(ctx,address,v.export_public(peer,peerkey))
                    v.pin_contact(ctx,address,fingerprint,'in-person')  # Controlled synthetic trust, not human review.
            access=AccountAccess(); native=Provider(root/'tmp/m2/target/debug/qumail-m5-provider.exe')
            compose=Compose(v,access,native); opener=OpenMessage(v,access,native)
            class Resolver:
                def resolve(self,handle,*values):
                    if handle.context not in [c for c,k in accounts]: raise ValueError('fixture context')
                    return SyntheticResolver(handle.context).resolve(handle,*values)
            with SMTPServer(path/'certs',args.scenario) as server:
                submit=SubmitOutbox(compose.repository,LoopbackSMTP('127.0.0.1',server.port,Resolver(),fixture_context=server.client_context))
                views=tuple(sorted((AccountView(*row) for row in v.summaries()),key=lambda v:[c for c,k in accounts].index(v.context)))
                panel=ComposePanel(DevelopmentSession(),access,compose,opener,submit,views)
                panel.to.setText('recipient@example.invalid'); panel.cc.setText('second@example.invalid')
                panel.subject.setText('Disposable protected subject'); panel.body.setPlainText('Disposable compose fixture')
                if not args.smoke: panel.show(); return app.exec()
                def run(action,**kw):
                    panel.start(action,**kw); until=time.monotonic()+35
                    while panel.pending and time.monotonic()<until: app.processEvents(); panel.poll(); time.sleep(.01)
                    assert not panel.pending
                run('draft'); run('prepare'); assert panel.shared
                run('submit')
                initial=panel.status.text().split(' · ')[0]
                expected={'success':'Accepted','auth-reject':'Failed','final-loss':'Unknown'}[args.scenario]
                assert initial==expected
                if initial!='Accepted':
                    run('recover'); run('retry',acknowledge_duplicate_risk=True)
                    server.mode='success'; run('submit'); assert panel.status.text().startswith('Accepted')
                for i in (1,2,0):
                    panel.select(i); run('open'); assert panel.content.toPlainText().endswith('Disposable compose fixture')
                    assert 'Signature valid' in panel.status.text()
                assert len(set(server.digests))==1
                print(json.dumps(dict(fixture_only=True,initial=initial,final='Accepted',recipient_copies=2,sender_archive=True,
                    persisted_bytes_match=True,private_content_logged=False)))
                return 0
        finally:
            if panel:
                panel.close(); app.processEvents(); panel.pool.shutdown(wait=True,cancel_futures=True)
            store.delete(v.ident)


if __name__=='__main__': raise SystemExit(main())
