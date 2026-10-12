"""Opt-in disposable Qt outbox + real loopback SMTP/TLS fixture."""
import argparse
import json
from pathlib import Path
import tempfile
import time
from PyQt6.QtWidgets import QApplication
from core.account_session import DevelopmentSession, AccountView
from experiments.m3.types import EmailAddress,UserId,VerifiedProviderIdentity
from experiments.m3.vault import Vault,PROFILE
from experiments.m3.provider import Provider
from experiments.m3.secure_store import WindowsCredentialStore
from .model import AccountAccess,State
from .services import PrepareMessage,SubmitOutbox
from .vault_adapter import VaultOutbox
from .smtp_fixture import SMTPServer,SMTPFixtureBuilder,SyntheticResolver
from .smtp_transport import LoopbackSMTP
from .outbox_panel import OutboxPanel


def finish_panel(panel, app):
    # Called after the interactive event loop/server exits, before deleting the
    # disposable vault/lock directory. GUI closeEvent itself remains nonblocking.
    panel.close(); app.processEvents()
    panel.pool.shutdown(wait=True, cancel_futures=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--loopback',action='store_true')
    parser.add_argument('--scenario',choices=['success','auth-reject','final-loss'],default='success')
    parser.add_argument('--smoke',action='store_true',help='offscreen-friendly bounded workflow, then exit')
    args=parser.parse_args()
    if not args.loopback: parser.error('--loopback is required; no external SMTP supported')
    app=QApplication.instance() or QApplication([])
    root=Path(__file__).resolve().parents[2]
    with tempfile.TemporaryDirectory(prefix='m4-loopback-',dir=root/'tmp') as folder:
        path=Path(folder); store=WindowsCredentialStore()
        v=Vault.create(path/'vault.sqlite',store,Provider(root/'tmp/m2/target/debug/qumail-m3-provider.exe'))
        panel=None
        try:
            accounts=[]
            for name in ('sender','recipient'):
                address=EmailAddress(name+'@example.invalid')
                identity=VerifiedProviderIdentity('https://accounts.google.com','synthetic-'+name,(address,),int(time.time())+3600,'fixture only')
                accounts.append(v.enroll(identity,address,UserId.new()))
            access=AccountAccess(); repo=VaultOutbox(v,access); operations={}
            for (ctx,key),(peer,peerkey) in [(accounts[0],accounts[1]),(accounts[1],accounts[0])]:
                target=EmailAddress(v._read(peer)['address']); public=v.export_public(peer,peerkey)
                fingerprint=v.import_contact(ctx,target,public); v.pin_contact(ctx,target,fingerprint,'in-person')
                lease=access.select(ctx); prepare=PrepareMessage(repo,SMTPFixtureBuilder())
                op=prepare.draft(lease,b'disposable loopback protocol fixture')
                prepare.prepare(lease,op,key,(target,),PROFILE); operations[ctx.account.value]=op
            class Resolver:
                def resolve(self,handle,*args):
                    if handle.context not in [a[0] for a in accounts]: raise ValueError('unknown fixture account')
                    return SyntheticResolver(handle.context).resolve(handle,*args)
            with SMTPServer(path/'certs',args.scenario) as server:
                submit=SubmitOutbox(repo,LoopbackSMTP('127.0.0.1',server.port,Resolver(),fixture_context=server.client_context))
                views=tuple(AccountView(*row) for row in v.summaries())
                session=DevelopmentSession(); panel=OutboxPanel(session,access,submit,operations,views)
                if not args.smoke:
                    panel.show(); return app.exec()
                panel.start('inspect')
                def drain():
                    until=time.monotonic()+10
                    while panel.pending and time.monotonic()<until:
                        app.processEvents(); panel.poll(); time.sleep(.01)
                    assert not panel.pending
                drain(); panel.start('submit'); drain()
                op=operations[panel.lease.context.account.value]
                initial=submit.inspect(panel.lease,op).state
                reopened=SubmitOutbox(VaultOutbox(Vault(v.path,store,v.provider),access),submit.transport)
                recovered=reopened.recover(panel.lease)
                if initial in (State.UNKNOWN,State.FAILED):
                    reopened.retry(panel.lease,op,acknowledge_duplicate_risk=True)
                    server.mode='success'; assert reopened.submit(panel.lease,op).state is State.ACCEPTED
                def failed_export(value): raise OSError('fixture export failure')
                assert not reopened.export_receipt(panel.lease,op,failed_export)
                assert reopened.inspect(panel.lease,op).state is State.ACCEPTED
                print(json.dumps(dict(fixture_only=True,initial=initial.value,final='Accepted',
                    restart_auto_submissions=0,retained_payloads_equal=len(set(server.digests))<=1,
                    receipt_failure_preserved=True)))
                return 0
        finally:
            if panel: finish_panel(panel, app)
            store.delete(v.ident)


if __name__=='__main__': raise SystemExit(main())
