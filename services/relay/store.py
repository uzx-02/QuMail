"""Single-host durable relay. Each operation owns a connection/transaction.

No cloud qualification is implied: SQLite WAL requires a local filesystem shared
by processes on ONE host. The network boundary supplies an authenticated Peer.
"""
from contextlib import closing, contextmanager
from dataclasses import dataclass
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time
import uuid

from experiments.m5.mime import parse_outer
from experiments.m5.model import Failure as MimeFailure, MAX_WIRE


class Code(str, Enum):
    INVALID = 'invalid_request'
    DENIED = 'not_authorized_or_unavailable'
    CONFLICT = 'idempotency_conflict'
    LIMIT = 'quota_exceeded'
    BACKEND = 'durable_backend_unavailable'


class Failure(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code.value)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise Failure(Code.INVALID)
    return value


@dataclass(frozen=True)
class Peer:
    principal: str
    device: str

    def __post_init__(self):
        identifier(self.principal)
        identifier(self.device)


@dataclass(frozen=True)
class Limits:
    total_objects: int = 1024
    principal_objects: int = 32
    total_bytes: int = 16 * 1024 * 1024
    principal_bytes: int = 2 * 1024 * 1024
    # Includes tombstones: exhausted databases fail closed until operator rotation.
    # Never automatically forget an idempotency key and recreate consumed data.
    total_records: int = 10000
    principal_records: int = 256


SCHEMA = '''
CREATE TABLE config(version INTEGER NOT NULL CHECK(version=1));
INSERT INTO config VALUES(1);
CREATE TABLE objects(
 id TEXT PRIMARY KEY, owner TEXT NOT NULL, owner_device TEXT NOT NULL,
 upload_key TEXT NOT NULL, request_digest TEXT NOT NULL,
 recipient TEXT NOT NULL, expires REAL NOT NULL,
 payload BLOB, size INTEGER NOT NULL,
 state TEXT NOT NULL CHECK(state IN ('ready','leased','consumed','expired')),
 lease_id TEXT, lease_device TEXT, lease_key TEXT, lease_until REAL,
 UNIQUE(owner,owner_device,upload_key));
CREATE INDEX owner_objects ON objects(owner);
'''


class Store:
    def __init__(self, path, *, clock=time.time, limits=Limits()):
        self.path = Path(path).resolve()
        self.clock, self.limits = clock, limits
        if not self.path.is_file():
            raise Failure(Code.BACKEND)
        # Readiness is a real durable write transaction, not an in-memory fallback.
        with self.transaction():
            pass

    @classmethod
    def create(cls, path, **kwargs):
        path = Path(path).resolve()
        # Explicit create only, refuses overwrite. Never silently initializes on outage.
        with path.open('xb'):
            pass
        try:
            with closing(sqlite3.connect(path)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('PRAGMA synchronous=FULL')
                db.executescript(SCHEMA)
        except sqlite3.Error:
            raise Failure(Code.BACKEND) from None
        return cls(path, **kwargs)

    @contextmanager
    def transaction(self):
        db = None
        try:
            db = sqlite3.connect(self.path.as_uri()+'?mode=rw', uri=True, timeout=3)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA secure_delete=ON')
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT version FROM config').fetchall()[0][0] != 1:
                raise Failure(Code.BACKEND)
            yield db
            db.commit()
        except (sqlite3.Error, OSError, IndexError):
            raise Failure(Code.BACKEND) from None
        finally:
            if db is not None:
                db.close()  # Rollback on any exception; connection never shared.

    def _expire(self, db, now):
        db.execute("UPDATE objects SET state='expired',payload=NULL WHERE payload IS NOT NULL "
                   "AND (expires<=? OR (state='leased' AND lease_until<=?))", (now, now))

    def sweep(self):
        with self.transaction() as db:
            self._expire(db, self.clock())

    def upload(self, peer, key, recipient, payload, ttl=3600):
        identifier(key); identifier(recipient)
        if type(ttl) is not int or not 1 <= ttl <= 86400:
            raise Failure(Code.INVALID)
        if not isinstance(payload, bytes) or not 0 < len(payload) <= MAX_WIRE:
            raise Failure(Code.LIMIT)
        try:
            outer, _ = parse_outer(payload)
            # Routing fields are visible; subject and arbitrary extra headers are not.
            allowed = {'from','to','cc','subject','date','message-id','mime-version','content-type'}
            if str(outer.headers.get('Subject')) != 'Encrypted message' or any(
                    name.lower() not in allowed for name in outer.headers.keys()):
                raise Failure(Code.INVALID)
        except MimeFailure:
            raise Failure(Code.INVALID) from None
        digest = hashlib.sha256(json.dumps([recipient,ttl], separators=(',',':')).encode()+payload).hexdigest()
        with self.transaction() as db:
            now = self.clock()  # After acquiring the database lock.
            self._expire(db, now)
            old = db.execute('SELECT * FROM objects WHERE owner=? AND owner_device=? AND upload_key=?',
                             (peer.principal,peer.device,key)).fetchone()
            if old:
                if old['request_digest'] != digest: raise Failure(Code.CONFLICT)
                return dict(id=old['id'], state=old['state'], expires=old['expires'])
            rows = db.execute('SELECT owner,size,payload IS NOT NULL AS active FROM objects').fetchall()
            own = [row for row in rows if row['owner'] == peer.principal]
            limits = self.limits
            for group, count, size, records in ((rows,limits.total_objects,limits.total_bytes,limits.total_records),
                                               (own,limits.principal_objects,limits.principal_bytes,limits.principal_records)):
                if len(group)>=records or sum(r['active'] for r in group)>=count or sum(
                        r['size'] for r in group if r['active'])+len(payload)>size:
                    raise Failure(Code.LIMIT)
            object_id = uuid.uuid4().hex
            db.execute('INSERT INTO objects(id,owner,owner_device,upload_key,request_digest,recipient,expires,payload,size,state) '
                       "VALUES(?,?,?,?,?,?,?,?,?,'ready')", (object_id,peer.principal,peer.device,key,digest,
                                                           recipient,now+ttl,payload,len(payload)))
            return dict(id=object_id,state='ready',expires=now+ttl)

    def lease(self, peer, object_id, key):
        identifier(object_id); identifier(key)
        with self.transaction() as db:
            now = self.clock()
            self._expire(db, now)
            row = db.execute('SELECT * FROM objects WHERE id=?', (object_id,)).fetchone()
            if row is None or row['recipient']!=peer.principal or row['state'] not in ('ready','leased'):
                raise Failure(Code.DENIED)
            if row['state']=='leased':
                if row['lease_device']!=peer.device or row['lease_key']!=key:
                    raise Failure(Code.DENIED)
                if min(row['expires'],row['lease_until'])<=self.clock():
                    raise Failure(Code.DENIED)
                return dict(lease=row['lease_id'],until=row['lease_until'])
            lease = uuid.uuid4().hex
            until = min(row['expires'],now+300)
            db.execute("UPDATE objects SET state='leased',lease_id=?,lease_device=?,lease_key=?,lease_until=? WHERE id=?",
                       (lease,peer.device,key,until,object_id))
            if until<=self.clock(): raise Failure(Code.DENIED)
            return dict(lease=lease,until=until)

    def _authorized(self, db, peer, object_id, lease_id, now, consumed=False):
        identifier(object_id); identifier(lease_id)
        row = db.execute('SELECT * FROM objects WHERE id=?', (object_id,)).fetchone()
        states = ('leased','consumed') if consumed else ('leased',)
        if (row is None or row['recipient']!=peer.principal or row['lease_device']!=peer.device
                or row['lease_id']!=lease_id or row['state'] not in states
                or row['expires']<=now or row['lease_until']<=now):
            raise Failure(Code.DENIED)
        return row

    def download(self, peer, object_id, lease_id):
        with self.transaction() as db:
            now = self.clock()
            self._expire(db, now)
            row = self._authorized(db,peer,object_id,lease_id,now)
            self._authorized(db,peer,object_id,lease_id,self.clock())
            return bytes(row['payload'])

    def acknowledge(self, peer, object_id, lease_id):
        with self.transaction() as db:
            now = self.clock()
            self._expire(db, now)
            self._authorized(db,peer,object_id,lease_id,now,consumed=True)
            db.execute("UPDATE objects SET state='consumed',payload=NULL WHERE id=?", (object_id,))
            self._authorized(db,peer,object_id,lease_id,self.clock(),consumed=True)
        return dict(state='consumed')
