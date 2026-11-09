"""Bounded RFC 3156 combined PGP/MIME + RFC 9788 cryptographic payload.

Deliberately narrow experimental profile, not a general-purpose mail renderer.
All metadata is inside provider-authenticated bytes. No OpenPGP packet encoding.
"""
import base64
from dataclasses import dataclass
from email.message import EmailMessage
from email.parser import BytesHeaderParser
from email.policy import SMTP
from email.utils import parsedate_to_datetime
import re
from experiments.m3.types import EmailAddress
from .model import *

POLICY=SMTP.clone(max_line_length=78,raise_on_defect=True)
REQUIRED=('From','To','Subject','Date','Message-ID','X-QuMail-Profile','X-QuMail-Archive')
OPTIONAL=('Cc','In-Reply-To','References')
STRUCTURAL=('content-type','content-transfer-encoding','mime-version','content-disposition')
SINGLETONS={x.lower() for x in REQUIRED+OPTIONAL+STRUCTURAL}


def fail(code=Code.INVALID, reason=""):
    import inspect
    frame = inspect.currentframe().f_back
    print(f"[MIME FAIL]: code={code} at line {frame.f_lineno} reason={reason!r}")
    raise Failure(code)


def text(value, limit=512):
    if not isinstance(value,str) or len(value.encode('utf-8'))>limit or any(ord(c)<32 or ord(c)==127 for c in value): fail()
    return value


def address(value):
    try: return EmailAddress(text(value,254)).value
    except Exception: fail(Code.IDENTITY)


def message_id(value):
    if not re.fullmatch(r'<[A-Za-z0-9._+-]{1,100}@[A-Za-z0-9.-]{1,100}>',text(value,210)): fail()
    return value


def validate(draft):
    if type(draft) is not Draft or type(draft.archive) is not bool: fail()
    if draft.bcc: fail(Code.PROFILE)
    recipients=draft.to+draft.cc
    if not draft.to or not 1<=len(recipients)<=MAX_RECIPIENTS or len(set(recipients))!=len(recipients): fail(Code.LIMIT)
    if any(address(v)!=v for v in recipients): fail()
    text(draft.subject)
    if type(draft.body) is not str or len(draft.body.encode())>MAX_BODY or '\x00' in draft.body: fail(Code.LIMIT)
    if len(draft.attachments)>MAX_ATTACHMENTS or sum(len(a.data) for a in draft.attachments)>MAX_ATTACHMENT_BYTES: fail(Code.LIMIT)
    for a in draft.attachments:
        if type(a) is not Attachment or type(a.data) is not bytes: fail()
        if not isinstance(a.name,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._ -]{0,63}',a.name) or '..' in a.name: fail()
        if a.media_type not in ('application/octet-stream','text/plain','image/png','application/pdf'): fail(Code.PROFILE)
    if draft.in_reply_to: message_id(draft.in_reply_to)
    if len(draft.references)>8: fail(Code.LIMIT)
    for ref in draft.references: message_id(ref)


def outer_fields(sender,draft,ident,date):
    fields=[('From',address(sender)),('To',', '.join(draft.to))]
    if draft.cc: fields.append(('Cc',', '.join(draft.cc)))
    return fields+[('Subject','Encrypted message'),('Date',date),('Message-ID',ident)]


def build_inner(sender,draft,ident,date):
    validate(draft); message_id(ident); text(date,80)
    if parsedate_to_datetime(date).tzinfo is None: fail()
    m=EmailMessage(policy=POLICY)
    for k,v in outer_fields(sender,draft,ident,date): m[k]=draft.subject if k=='Subject' else v
    m['X-QuMail-Profile']=PROFILE
    m['X-QuMail-Archive']=address(sender) if draft.archive else 'none'
    if draft.in_reply_to: m['In-Reply-To']=draft.in_reply_to
    if draft.references: m['References']=' '.join(draft.references)
    m.set_content(draft.body.encode('utf-8'),maintype='text',subtype='plain',cte='base64')
    m.set_param('charset','utf-8')
    for a in draft.attachments:
        main,sub=a.media_type.split('/')
        m.add_attachment(a.data,maintype=main,subtype=sub,filename=a.name,cte='base64')
    m.set_param('hp','cipher',header='Content-Type')
    for k,v in outer_fields(sender,draft,ident,date): m['HP-Outer']=k+': '+v
    raw=m.as_bytes()
    if len(raw)>MAX_INNER: fail(Code.LIMIT)
    parse_inner(raw)  # Writer/reader agreement before any cryptographic operation.
    return raw


def build_outer(sender,draft,ident,date,armor):
    # Sequoia owns ASCII armor. Canonicalize text line endings, never packet bytes.
    armor=armor.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')
    m=EmailMessage(policy=POLICY)
    for k,v in outer_fields(sender,draft,ident,date): m[k]=v
    m['MIME-Version']='1.0'; m.set_type('multipart/encrypted')
    m.set_param('protocol','application/pgp-encrypted')
    control=EmailMessage(policy=POLICY); control.set_type('application/pgp-encrypted')
    control['Content-Transfer-Encoding']='7bit'; control.set_payload('Version: 1\r\n')
    data=EmailMessage(policy=POLICY); data.set_type('application/octet-stream')
    data['Content-Transfer-Encoding']='7bit'; data.set_payload(armor.decode('ascii'))
    m.attach(control); m.attach(data)
    raw=m.as_bytes()
    if len(raw)>MAX_WIRE: fail(Code.LIMIT)
    parse_outer(raw)
    return raw


@dataclass(frozen=True,repr=False)
class Node:
    headers: object
    body: bytes
    children: tuple


def parse(raw, maximum):
    if type(raw) is not bytes or len(raw)>maximum: fail(Code.LIMIT)
    if not raw or b'\x00' in raw or not raw.isascii() or b'\n' in raw.replace(b'\r\n',b'') or b'\r' in raw.replace(b'\r\n',b''): fail()
    if any(len(line)>998 for line in raw.split(b'\r\n')): fail(Code.LIMIT)
    counts=[0,0]
    def node(data,depth):
        counts[0]+=1
        if depth>MAX_DEPTH or counts[0]>MAX_PARTS: fail(Code.LIMIT)
        head,sep,body=data.partition(b'\r\n\r\n')
        counts[1]+=len(head)
        if not sep or counts[1]>MAX_HEADERS: fail(Code.LIMIT)
        try:
            h=BytesHeaderParser(policy=POLICY).parsebytes(head+b'\r\n\r\n')
            if h.defects: fail()
            for name in h.keys():
                if name.lower() in SINGLETONS and len(h.get_all(name))!=1:
                    fail(reason=f"duplicate singleton header {name}")
                if any(getattr(value,'defects',()) for value in h.get_all(name)): fail()
            for name,value in h.raw_items():
                if name.lower() in ('content-type','content-disposition'):
                    keys=re.findall(r';\s*([a-z0-9*_-]+)\s*=',value.lower())
                    if len(keys)!=len(set(keys)): fail()
        except Failure: raise
        except Exception: fail()
        children=[]
        if h.get_content_maintype()=='multipart':
            if h.get('Content-Transfer-Encoding','7bit').lower()!='7bit': fail()
            boundary=h.get_boundary()
            if not boundary or len(boundary)>70 or not re.fullmatch(r'[A-Za-z0-9_=+.-]+',boundary): fail()
            marker=b'--'+boundary.encode(); parts=[]; current=None; closed=False
            for line in body.splitlines(keepends=True):
                stripped=line.rstrip(b'\r\n')
                if stripped in (marker,marker+b'--'):
                    if closed: fail()
                    if current is not None: parts.append(b''.join(current))
                    current=[]
                    if stripped==marker+b'--': closed=True; current=None
                elif current is not None: current.append(line)
                elif line.strip(): fail()  # No ambiguous preamble/epilogue in this profile.
            if not closed or not parts: fail()
            if len(parts)+counts[0]>MAX_PARTS: fail(Code.LIMIT)
            children=[node(part,depth+1) for part in parts]
        elif h.get_content_maintype()=='message': fail(Code.PROFILE)
        return Node(h,body,tuple(children))
    return node(raw,1)


def only_headers(node,allowed):
    if any(k.lower() not in allowed for k in node.headers.keys()): fail(Code.PROFILE)


def parameters(node,allowed):
    values=node.headers.get_params() or []
    if any(k.lower() not in allowed for k,v in values[1:]): fail(Code.PROFILE)


def parse_outer(raw):
    n=parse(raw,MAX_WIRE); h=n.headers
    if h.get_content_type()!='multipart/encrypted' or h.get_param('protocol')!='application/pgp-encrypted' or len(n.children)!=2: fail()
    if h.get_param('hp') is not None or h.get_all('HP-Outer') or h.get('Bcc'): fail()
    if set(k for k,v in h.get_params())!={'multipart/encrypted','protocol','boundary'}: fail()
    a,b=n.children
    for child in (a,b):
        only_headers(child,set(STRUCTURAL))
        parameters(child,set())
        if child.children or child.headers.get('Content-Transfer-Encoding','7bit').lower()!='7bit': fail()
    if a.headers.get_content_type()!='application/pgp-encrypted' or a.body.rstrip(b'\r\n')!=b'Version: 1': fail()
    if b.headers.get_content_type()!='application/octet-stream': fail()
    armor=b.body.strip(b'\r\n')+b'\r\n'
    if (not armor.startswith(b'-----BEGIN PGP MESSAGE-----\r\n') or
        not armor.endswith(b'-----END PGP MESSAGE-----\r\n') or armor.count(b'-----BEGIN')!=1 or armor.count(b'-----END')!=1): fail()
    return n,armor


def addresses(value):
    result=tuple(address(v.strip()) for v in str(value).split(','))
    if len(set(result))!=len(result): fail()
    return result


def decoded(node):
    if node.headers.get('Content-Transfer-Encoding','').lower()!='base64': fail(Code.PROFILE)
    try: return base64.b64decode(b''.join(node.body.split()),validate=True)
    except Exception: fail()


def parse_inner(raw):
    n=parse(raw,MAX_INNER); h=n.headers
    only_headers(n,{x.lower() for x in REQUIRED+OPTIONAL+('HP-Outer',)+STRUCTURAL})
    if any(h.get(name) is None for name in REQUIRED): fail()
    if str(h['X-QuMail-Profile'])!=PROFILE: fail(Code.PROFILE)
    if h.get_param('hp')!='cipher' or h.get('MIME-Version')!='1.0': fail(Code.PROFILE)
    parameters(n,{'boundary','hp'} if n.children else {'charset','hp'})
    sender=address(str(h['From'])); to=addresses(h['To']); cc=addresses(h['Cc']) if h.get('Cc') else ()
    ident=message_id(str(h['Message-ID'])); date=text(str(h['Date']),80)
    try:
        if parsedate_to_datetime(date).tzinfo is None: fail()
    except Exception: fail()
    archive=str(h['X-QuMail-Archive'])
    if archive not in ('none',sender): fail(Code.IDENTITY)
    parts=n.children if n.children else (n,)
    if n.children and h.get_content_type()!='multipart/mixed': fail(Code.PROFILE)
    body=parts[0]
    if body.headers.get_content_type()!='text/plain' or body.headers.get_content_charset()!='utf-8' or body.children: fail(Code.PROFILE)
    if n.children: only_headers(body,set(STRUCTURAL))
    parameters(body,{'charset'} if n.children else {'charset','hp'})
    try: plain=decoded(body).decode('utf-8')
    except UnicodeError: fail()
    attachments=[]
    for part in parts[1:]:
        only_headers(part,set(STRUCTURAL))
        parameters(part,set())
        if part.children or part.headers.get_content_disposition()!='attachment': fail()
        attachments.append(Attachment(part.headers.get_filename(),part.headers.get_content_type(),decoded(part)))
    draft=Draft(to,cc,text(str(h['Subject'])),plain,tuple(attachments),str(h.get('In-Reply-To','')),
                tuple(str(h.get('References','')).split()),archive!='none')
    validate(draft)
    snapshots={}
    for value in h.get_all('HP-Outer',[]):
        key,sep,val=str(value).partition(': ')
        key=key.lower()
        if not sep or key in snapshots or key not in ('from','to','cc','subject','date','message-id'): fail()
        snapshots[key]=val
    expected={k.lower():v for k,v in outer_fields(sender,draft,ident,date)}
    if snapshots!=expected: fail()  # Exact declared development confidentiality policy.
    return sender,draft,ident,date,snapshots


def mismatches(outer,snapshots):
    names=set(snapshots)|{'cc','in-reply-to','references','x-qumail-profile','x-qumail-archive'}
    return tuple(sorted(k for k in names if str(outer.headers.get(k,''))!=snapshots.get(k,'')))
