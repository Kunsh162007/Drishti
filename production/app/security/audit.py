"""Tamper-evident, hash-chained audit ledger.

entry_hash = SHA-256(prev_hash + canonical_json(payload)). Any in-place edit or
deletion of a past row breaks the chain, which verify_chain() detects and locates.

The pure helpers (hash_entry / verify_entries) take plain dicts so the chain can be
unit-tested without a database.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..models import AuditLog

GENESIS = "0" * 64


def _ts_iso(dt) -> str:
    """Normalise a datetime to a UTC ISO string that round-trips across SQLite/Postgres."""
    if dt is None:
        return ""
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def payload(seq, ts_iso, user, action, resource, detail) -> dict:
    return {"seq": seq, "ts": ts_iso, "user": user, "action": action,
            "resource": resource, "detail": detail}


def hash_entry(prev_hash: str, p: dict) -> str:
    return hashlib.sha256((prev_hash + json.dumps(p, sort_keys=True, default=str)).encode()).hexdigest()


def verify_entries(entries: list[dict]) -> dict:
    """Verify an ordered list of entry dicts (each with payload fields + prev_hash + entry_hash)."""
    prev = GENESIS
    for e in entries:
        p = payload(e["seq"], e["ts"], e["user"], e["action"], e["resource"], e["detail"])
        if e["prev_hash"] != prev or hash_entry(prev, p) != e["entry_hash"]:
            return {"valid": False, "count": len(entries), "broken_at": e["seq"],
                    "head_hash": entries[-1]["entry_hash"] if entries else GENESIS}
        prev = e["entry_hash"]
    return {"valid": True, "count": len(entries), "broken_at": None, "head_hash": prev}


# ---- DB-backed API --------------------------------------------------------------------------
def append(db: Session, user: str, action: str, resource: str, detail: str = "") -> AuditLog:
    last = db.query(AuditLog).order_by(AuditLog.seq.desc()).first()
    seq = (last.seq + 1) if last else 1
    prev = last.entry_hash if last else GENESIS
    ts = datetime.now(timezone.utc)
    p = payload(seq, _ts_iso(ts), user, action, resource, detail)
    entry_hash = hash_entry(prev, p)
    row = AuditLog(seq=seq, ts=ts, user=user, action=action, resource=resource,
                   detail=detail, prev_hash=prev, entry_hash=entry_hash)
    db.add(row)
    db.commit()
    return row


def verify_chain(db: Session) -> dict:
    rows = db.query(AuditLog).order_by(AuditLog.seq.asc()).all()
    entries = [{"seq": r.seq, "ts": _ts_iso(r.ts), "user": r.user, "action": r.action,
                "resource": r.resource, "detail": r.detail, "prev_hash": r.prev_hash,
                "entry_hash": r.entry_hash} for r in rows]
    return verify_entries(entries)
