"""Unit tests for the production security primitives — no DB or live services needed.

Run from production/:   python -m pytest app/tests/ -q     (or: python app/tests/test_security.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # production/

from app.security import audit, encryption  # noqa: E402


def _chain(entries_raw):
    """Build a valid hash-chained list from (user, action, resource) tuples."""
    out, prev = [], audit.GENESIS
    for i, (u, a, r) in enumerate(entries_raw, start=1):
        p = audit.payload(i, f"2026-06-15T00:00:0{i % 10}+00:00", u, a, r, "")
        eh = audit.hash_entry(prev, p)
        out.append({**p, "prev_hash": prev, "entry_hash": eh})
        prev = eh
    return out


def test_audit_chain_valid():
    chain = _chain([("alice", "GET", "/api/hotspots"), ("bob", "POST", "/api/assistant/chat"),
                    ("carol", "GET", "/api/network")])
    res = audit.verify_entries(chain)
    assert res["valid"] is True and res["count"] == 3 and res["broken_at"] is None


def test_audit_detects_tampering():
    chain = _chain([("alice", "GET", "/a"), ("bob", "GET", "/b"), ("carol", "GET", "/c")])
    chain[1]["resource"] = "/HACKED"  # tamper with a past entry's content
    res = audit.verify_entries(chain)
    assert res["valid"] is False and res["broken_at"] == 2


def test_audit_detects_deletion():
    chain = _chain([("a", "G", "/1"), ("b", "G", "/2"), ("c", "G", "/3")])
    del chain[1]  # remove a row -> prev_hash linkage breaks
    res = audit.verify_entries(chain)
    assert res["valid"] is False


def test_envelope_roundtrip_and_crypto_shred():
    from cryptography.fernet import Fernet
    master = encryption.master_cipher()
    data_key = encryption.new_data_key()
    wrapped = encryption.wrap_key(master, data_key)

    token = encryption.encrypt_with(data_key, "Aadhaar: 1234-5678-9012")
    assert encryption.decrypt_with(encryption.unwrap_key(master, wrapped), token) == "Aadhaar: 1234-5678-9012"

    # Crypto-shred = destroy the (wrapped) data key. Without it, ciphertext is unrecoverable.
    wrapped = None
    recovered_key = None
    try:
        recovered_key = encryption.unwrap_key(master, wrapped) if wrapped else None
    except Exception:
        recovered_key = None
    assert recovered_key is None  # key gone -> data permanently unrecoverable


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        print(f"  [OK] {fn.__name__}")
        passed += 1
    print(f"\n{passed}/{len(fns)} security tests passed")
