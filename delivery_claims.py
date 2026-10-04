"""Durable at-most-once delivery attempts, independent of the Actions checkout.

FULL synchronous SQLite commits plus explicit file/directory fsync precede sends.
An ambiguous attempt is never expired or automatically retried. Operator-only
reconciliation is required; receipts aren't proof that a remote API didn't fail.
"""
import argparse
import json
from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import uuid

DEFAULT_DB = Path.home()/'.local/state/yt-hermes-runner/delivery.sqlite'
CHECKOUT = Path(__file__).resolve().parent


class DeliveryBlocked(RuntimeError):
    pass


def fsync_path(path):
    for target, flags in [(path, os.O_RDONLY), (path.parent, os.O_RDONLY | os.O_DIRECTORY)]:
        fd = os.open(target, flags)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class DeliveryClaims:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get('YT_DELIVERY_DB') or DEFAULT_DB).absolute()
        if self.path.is_symlink() or self.path.resolve().is_relative_to(CHECKOUT):
            raise DeliveryBlocked('Delivery state must be outside checkout, not a symlink')
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self._transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts (token TEXT PRIMARY KEY, kind TEXT NOT NULL, '
                       'status TEXT NOT NULL, receipt TEXT, created_at TEXT NOT NULL, completed_at TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS reconciliations (token TEXT NOT NULL, decision TEXT NOT NULL, '
                       'note TEXT NOT NULL, identities TEXT NOT NULL, recorded_at TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS identities (kind TEXT, identity TEXT, token TEXT NOT NULL '
                       'REFERENCES attempts(token), PRIMARY KEY(kind,identity))')
        os.chmod(self.path, 0o600)
        fsync_path(self.path)

    @contextmanager
    def _transaction(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('PRAGMA foreign_keys=ON')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.execute('COMMIT')
        except BaseException:
            if db.in_transaction: db.execute('ROLLBACK')
            raise
        finally:
            db.close()
        fsync_path(self.path)

    def start(self, kind, identities):
        keys = sorted(set(identities))
        if kind not in {'upload', 'comment'} or not keys or any(not isinstance(k,str) or not k.strip() for k in keys):
            raise DeliveryBlocked('Stable delivery identities required')
        with self._transaction() as db:
            rows = [db.execute('SELECT a.status,a.receipt,a.token FROM identities i JOIN attempts a ON a.token=i.token '
                               'WHERE i.kind=? AND i.identity=?', (kind,key)).fetchone() for key in keys]
            rows = [row for row in rows if row]
            active_rows = [row for row in rows if row[0] != 'reconciled_not_delivered']
            if active_rows:
                rows = active_rows
                receipts = {receipt for status,receipt,_ in rows if status == 'completed'}
                if any(status != 'completed' for status,_,_ in rows) or len(receipts) != 1:
                    raise DeliveryBlocked('Unresolved or conflicting delivery; operator reconciliation required')
                # A later story may add aliases for the same remote publication.
                # Bind them too, otherwise a subsequent single-alias retry sends again.
                token = rows[0][2]
                db.executemany('INSERT OR REPLACE INTO identities VALUES(?,?,?)',
                               [(kind,key,token) for key in keys])
                return None, receipts.pop()
            if db.execute("SELECT 1 FROM attempts WHERE kind=? AND status='attempted' LIMIT 1",(kind,)).fetchone():
                raise DeliveryBlocked('Unresolved prior delivery; operator reconciliation required')
            token = uuid.uuid4().hex
            db.execute('INSERT INTO attempts(token,kind,status,created_at) VALUES(?,?,?,?)',
                       (token,kind,'attempted',datetime.now(timezone.utc).isoformat()))
            db.executemany('INSERT OR REPLACE INTO identities VALUES(?,?,?)', [(kind,key,token) for key in keys])
        return token, None

    def complete(self, token, receipt):
        if not isinstance(receipt,str) or not receipt.strip():
            raise DeliveryBlocked('Valid remote receipt required')
        with self._transaction() as db:
            changed = db.execute("UPDATE attempts SET status='completed',receipt=?,completed_at=? "
                                 "WHERE token=? AND status='attempted'", (receipt,datetime.now(timezone.utc).isoformat(),token)).rowcount
            if changed != 1:
                raise DeliveryBlocked('Attempt ownership/state mismatch')

    def reconcile(self, token, decision, note, receipt=None):
        """Explicit operator assertion after remote audit; never infer absence.

        No network calls. A human must verify the correct channel, all remote
        pages and upload processing states. Unknown delivery remains blocked.
        """
        if (decision not in {'delivered','not-delivered'} or not isinstance(note,str)
                or len(note.strip()) < 20 or (decision == 'delivered' and
                (not isinstance(receipt,str) or not receipt.strip()))):
            raise DeliveryBlocked('Explicit decision, evidence note and delivered receipt required')
        with self._transaction() as db:
            row = db.execute('SELECT status FROM attempts WHERE token=?',(token,)).fetchone()
            if not row or row[0] != 'attempted': raise DeliveryBlocked('Only unresolved attempt can be reconciled')
            identities = [r[0] for r in db.execute('SELECT identity FROM identities WHERE token=?',(token,))]
            now = datetime.now(timezone.utc).isoformat()
            db.execute('INSERT INTO reconciliations VALUES(?,?,?,?,?)',
                       (token,decision,note.strip(),json.dumps(identities),now))
            db.execute('UPDATE attempts SET status=?,receipt=?,completed_at=? WHERE token=?',
                       ('completed' if decision == 'delivered' else 'reconciled_not_delivered',
                        receipt if decision == 'delivered' else None,now,token))


def main():
    parser = argparse.ArgumentParser(description='Operator-only offline delivery reconciliation; never sends')
    parser.add_argument('--db',default=str(DEFAULT_DB))
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('inspect')
    reconcile = sub.add_parser('reconcile')
    reconcile.add_argument('--token',required=True)
    reconcile.add_argument('--decision',choices=['delivered','not-delivered'],required=True)
    reconcile.add_argument('--note',required=True)
    reconcile.add_argument('--receipt')
    args = parser.parse_args()
    path = Path(args.db)
    if not path.is_file(): raise DeliveryBlocked('Existing ledger required; no empty reset')
    claims = DeliveryClaims(path)
    if args.command == 'inspect':
        with sqlite3.connect(path.absolute().as_uri()+'?mode=ro',uri=True) as db:
            db.row_factory = sqlite3.Row
            print(json.dumps([dict(row) for row in db.execute('SELECT * FROM attempts')],indent=2))
    else:
        claims.reconcile(args.token,args.decision,args.note,args.receipt)
        print('Operator reconciliation recorded; no delivery attempted')


if __name__ == '__main__': main()
