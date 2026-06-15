"""Field-level PII encryption with envelope encryption + crypto-shred.

A master key (from config / HSM-KMS in production) wraps a per-record *data key*.
Fields are encrypted under the data key. Destroying the wrapped data key
(``crypto_shred``) makes every field encrypted under it permanently unrecoverable —
a cryptographic erase per NIST SP 800-88 Rev.1 (Purge), the safe realisation of
"stolen data is useless / right to erasure".

Low-level helpers are pure (no DB) so they can be unit-tested directly.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from ..config import settings
from ..models import KeyStore


class ShreddedError(RuntimeError):
    """Raised when decryption is attempted against a crypto-shredded record."""


# ---- pure key primitives --------------------------------------------------------------------
def new_data_key() -> bytes:
    return Fernet.generate_key()


def wrap_key(master: Fernet, data_key: bytes) -> str:
    return master.encrypt(data_key).decode()


def unwrap_key(master: Fernet, wrapped: str) -> bytes:
    return master.decrypt(wrapped.encode())


def encrypt_with(data_key: bytes, plaintext: str) -> str:
    return Fernet(data_key).encrypt(plaintext.encode()).decode()


def decrypt_with(data_key: bytes, token: str) -> str:
    return Fernet(data_key).decrypt(token.encode()).decode()


# ---- master key -----------------------------------------------------------------------------
def _derive_dev_key() -> bytes:
    # Deterministic DEV-ONLY key when MASTER_ENCRYPTION_KEY is unset. NEVER use in production.
    return base64.urlsafe_b64encode(hashlib.sha256(b"drishti-dev-master").digest())


def master_cipher() -> Fernet:
    key = settings.MASTER_ENCRYPTION_KEY.strip()
    return Fernet(key.encode() if key else _derive_dev_key())


# ---- DB-backed envelope API -----------------------------------------------------------------
def _get_or_create_data_key(db: Session, record_ref: str) -> bytes:
    master = master_cipher()
    ks = db.query(KeyStore).filter(KeyStore.record_ref == record_ref).first()
    if ks and ks.destroyed:
        raise ShreddedError(f"record {record_ref} has been crypto-shredded")
    if ks and ks.wrapped_data_key:
        return unwrap_key(master, ks.wrapped_data_key)
    dk = new_data_key()
    wrapped = wrap_key(master, dk)
    if ks:
        ks.wrapped_data_key = wrapped
    else:
        db.add(KeyStore(record_ref=record_ref, wrapped_data_key=wrapped, destroyed=False))
    db.commit()
    return dk


def encrypt_field(db: Session, record_ref: str, plaintext: str) -> str:
    return encrypt_with(_get_or_create_data_key(db, record_ref), plaintext)


def decrypt_field(db: Session, record_ref: str, token: str) -> str:
    master = master_cipher()
    ks = db.query(KeyStore).filter(KeyStore.record_ref == record_ref).first()
    if not ks or ks.destroyed or not ks.wrapped_data_key:
        raise ShreddedError(f"no usable key for {record_ref}")
    try:
        return decrypt_with(unwrap_key(master, ks.wrapped_data_key), token)
    except InvalidToken as e:
        raise ShreddedError(str(e))


def crypto_shred(db: Session, record_ref: str) -> dict:
    """Destroy the wrapped data key: all fields under it become unrecoverable."""
    ks = db.query(KeyStore).filter(KeyStore.record_ref == record_ref).first()
    if not ks:
        return {"record_ref": record_ref, "shredded": False, "reason": "no key record"}
    ks.wrapped_data_key = None
    ks.destroyed = True
    db.commit()
    return {"record_ref": record_ref, "shredded": True,
            "note": "Data key destroyed (NIST SP 800-88 Purge); ciphertext is now unrecoverable."}
