"""Tamper-evident, hash-chained audit ledger (demo realisation of the proposal's audit ledger).

Each entry stores entry_hash = SHA-256(prev_hash + canonical(entry)). Any later edit/deletion
breaks the chain, which verify_chain() detects and locates. Append-only; never updated in place.
"""
import hashlib
import json
from datetime import datetime, timezone

from .models import AuditLog

GENESIS = "0" * 64


def _hash(prev_hash: str, payload: dict) -> str:
    blob = prev_hash + json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def append(db, user: str, action: str, resource: str, detail: str = "") -> AuditLog:
    last = db.query(AuditLog).order_by(AuditLog.seq.desc()).first()
    seq = (last.seq + 1) if last else 1
    prev = last.entry_hash if last else GENESIS
    ts = datetime.now(timezone.utc).isoformat()
    payload = {"seq": seq, "ts": ts, "user": user, "action": action,
               "resource": resource, "detail": detail}
    entry_hash = _hash(prev, payload)
    row = AuditLog(seq=seq, ts=ts, user=user, action=action, resource=resource,
                   detail=detail, prev_hash=prev, entry_hash=entry_hash)
    db.add(row)
    db.commit()
    return row


def verify_chain(db) -> dict:
    """Recompute the whole chain to prove nothing was altered or deleted."""
    rows = db.query(AuditLog).order_by(AuditLog.seq.asc()).all()
    prev = GENESIS
    for r in rows:
        payload = {"seq": r.seq, "ts": r.ts, "user": r.user, "action": r.action,
                   "resource": r.resource, "detail": r.detail}
        if r.prev_hash != prev or _hash(prev, payload) != r.entry_hash:
            return {"valid": False, "count": len(rows), "broken_at": r.seq,
                    "head_hash": rows[-1].entry_hash if rows else GENESIS}
        prev = r.entry_hash
    return {"valid": True, "count": len(rows), "broken_at": None, "head_hash": prev}
