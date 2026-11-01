"""Isolated worker. No secrets in argv, diagnostics, temporary files or caches."""
import json
import sys


def run(request):
    if request['op']=='dns':
        import socket
        if (request['host'],request['port']) not in [('imap.gmail.com',993),('smtp.gmail.com',587)]:
            raise ValueError('endpoint')
        return socket.getaddrinfo(request['host'],request['port'],type=socket.SOCK_STREAM)[:16]
    from dataclasses import asdict
    import threading
    from transport.development_google import GoogleAuthorization
    from experiments.m3.types import AccountContext,AccountId,DeviceId
    provider=GoogleAuthorization(request['config'],request['scopes'])
    cancel=threading.Event()  # Parent terminates the whole worker on cancellation.
    if request['op']=='authorize':
        result=provider.authorize(cancel,request['address'],request['subject'])
    elif request['op']=='refresh':
        c=request['context']
        context=AccountContext(AccountId(c['account']['value']),DeviceId(c['device']['value']),c['issuer'],c['subject'])
        result=provider.refresh(cancel,context,request['address'],request['tokens'])
    else: raise ValueError('operation')
    return asdict(result)


if __name__=='__main__':
    try:
        raw=sys.stdin.buffer.read(1024*1024+1)
        if len(raw)>1024*1024: raise ValueError('input limit')
        print(json.dumps(dict(ok=True,value=run(json.loads(raw))),separators=(',',':')))
    except Exception as error:
        from experiments.m3.types import BoundaryError
        # Fixed application enums only; never provider diagnostics/callback URLs.
        code=error.code.value if isinstance(error,BoundaryError) else None
        print(json.dumps(dict(ok=False,code=code),separators=(',',':')))
