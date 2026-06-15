"""ORM models for the production store.

Crime/Person/Vehicle mirror the canonical schema in demo/SPEC.md (Postgres
types). User/AuditLog/KeyStore add production-grade auth, tamper-evident audit,
and crypto-shred key custody.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- canonical --
class Crime(Base):
    __tablename__ = "crimes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    fir_number: Mapped[str] = mapped_column(String, unique=True, index=True)
    district: Mapped[str | None] = mapped_column(String, index=True)
    police_station: Mapped[str | None] = mapped_column(String, index=True)
    crime_type: Mapped[str | None] = mapped_column(String, index=True)
    crime_category: Mapped[str | None] = mapped_column(String, index=True)
    severity: Mapped[int | None] = mapped_column(Integer)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    h3_r7: Mapped[str | None] = mapped_column(String, index=True)
    h3_r8: Mapped[str | None] = mapped_column(String, index=True)
    h3_r9: Mapped[str | None] = mapped_column(String, index=True)
    occurred_at: Mapped[str | None] = mapped_column(String, index=True)
    reported_at: Mapped[str | None] = mapped_column(String)
    hour: Mapped[int | None] = mapped_column(Integer, index=True)
    day_of_week: Mapped[int | None] = mapped_column(Integer)
    modus_operandi: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String, index=True)
    victim_count: Mapped[int | None] = mapped_column(Integer)
    accused_count: Mapped[int | None] = mapped_column(Integer)
    property_value_inr: Mapped[float | None] = mapped_column(Float, nullable=True)
    weapon_used: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str | None] = mapped_column(String)

    COLS = [
        "fir_number", "district", "police_station", "crime_type", "crime_category",
        "severity", "latitude", "longitude", "h3_r7", "h3_r8", "h3_r9", "occurred_at",
        "reported_at", "hour", "day_of_week", "modus_operandi", "description", "status",
        "victim_count", "accused_count", "property_value_inr", "weapon_used", "source",
    ]

    def as_dict(self) -> dict:
        return {c: getattr(self, c) for c in self.COLS}


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    person_id: Mapped[str | None] = mapped_column(String, index=True)
    fir_number: Mapped[str | None] = mapped_column(String, index=True)
    full_name: Mapped[str | None] = mapped_column(String, index=True)
    normalized_name: Mapped[str | None] = mapped_column(String, index=True)
    role: Mapped[str | None] = mapped_column(String, index=True)
    gender: Mapped[str | None] = mapped_column(String)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    district: Mapped[str | None] = mapped_column(String)
    true_identity_id: Mapped[str | None] = mapped_column(String, index=True)

    COLS = [
        "person_id", "fir_number", "full_name", "normalized_name", "role", "gender",
        "age", "phone", "address", "district", "true_identity_id",
    ]

    def as_dict(self) -> dict:
        return {c: getattr(self, c) for c in self.COLS}


class Vehicle(Base):
    __tablename__ = "vehicles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vehicle_id: Mapped[str | None] = mapped_column(String, index=True)
    fir_number: Mapped[str | None] = mapped_column(String, index=True)
    reg_number: Mapped[str | None] = mapped_column(String, index=True)
    vehicle_type: Mapped[str | None] = mapped_column(String)
    make_color: Mapped[str | None] = mapped_column(String, nullable=True)

    COLS = ["vehicle_id", "fir_number", "reg_number", "vehicle_type", "make_color"]

    def as_dict(self) -> dict:
        return {c: getattr(self, c) for c in self.COLS}


Index("ix_crimes_type_date", Crime.crime_type, Crime.occurred_at)


# ----------------------------------------------------------------- security --
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String, unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="constable", index=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AuditLog(Base):
    """Append-only, hash-chained audit ledger (tamper-evident).

    Each row links to the previous via ``prev_hash``; ``entry_hash`` is
    ``sha256(prev_hash + canonical_json(entry))``. Any in-place edit or deletion
    breaks the chain and is detected by ``verify_chain``.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seq: Mapped[int] = mapped_column(Integer, index=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    user: Mapped[str | None] = mapped_column(String, index=True)
    action: Mapped[str | None] = mapped_column(String, index=True)
    resource: Mapped[str | None] = mapped_column(String)
    detail: Mapped[str | None] = mapped_column(Text)
    prev_hash: Mapped[str | None] = mapped_column(String)
    entry_hash: Mapped[str | None] = mapped_column(String, index=True)

    __table_args__ = (UniqueConstraint("seq", name="uq_audit_seq"),)


class KeyStore(Base):
    """Per-record wrapped data keys for envelope encryption / crypto-shred.

    Destroying ``wrapped_data_key`` (setting ``destroyed=True`` and nulling the
    key) makes every field encrypted under it permanently unrecoverable — a
    cryptographic erase per NIST SP 800-88 (Purge).
    """

    __tablename__ = "key_store"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    record_ref: Mapped[str] = mapped_column(String, unique=True, index=True)
    wrapped_data_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    destroyed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# ----------------------------------------------------------- extended features --
class CDR(Base):
    __tablename__ = "cdr"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cdr_id: Mapped[str | None] = mapped_column(String, index=True)
    caller_msisdn: Mapped[str | None] = mapped_column(String, index=True)
    callee_msisdn: Mapped[str | None] = mapped_column(String, index=True)
    start_time: Mapped[str | None] = mapped_column(String, index=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    cell_tower_id: Mapped[str | None] = mapped_column(String, index=True)
    tower_lat: Mapped[float | None] = mapped_column(Float)
    tower_lng: Mapped[float | None] = mapped_column(Float)
    call_type: Mapped[str | None] = mapped_column(String)

    COLS = ["cdr_id", "caller_msisdn", "callee_msisdn", "start_time", "duration_sec",
            "cell_tower_id", "tower_lat", "tower_lng", "call_type"]

    def as_dict(self) -> dict:
        return {c: getattr(self, c) for c in self.COLS}


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[str | None] = mapped_column(String, index=True)
    holder_name: Mapped[str | None] = mapped_column(String)
    bank: Mapped[str | None] = mapped_column(String)
    district: Mapped[str | None] = mapped_column(String)
    is_mule: Mapped[bool | None] = mapped_column(Boolean)

    COLS = ["account_id", "holder_name", "bank", "district", "is_mule"]

    def as_dict(self) -> dict:
        return {c: getattr(self, c) for c in self.COLS}


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    txn_id: Mapped[str | None] = mapped_column(String, index=True)
    from_account: Mapped[str | None] = mapped_column(String, index=True)
    to_account: Mapped[str | None] = mapped_column(String, index=True)
    amount_inr: Mapped[float | None] = mapped_column(Float)
    timestamp: Mapped[str | None] = mapped_column(String, index=True)
    channel: Mapped[str | None] = mapped_column(String)
    fir_number: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    is_flagged: Mapped[bool | None] = mapped_column(Boolean)

    COLS = ["txn_id", "from_account", "to_account", "amount_inr", "timestamp",
            "channel", "fir_number", "is_flagged"]

    def as_dict(self) -> dict:
        return {c: getattr(self, c) for c in self.COLS}


class MissingPerson(Base):
    __tablename__ = "missing_persons"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mp_id: Mapped[str | None] = mapped_column(String, index=True)
    fir_number: Mapped[str | None] = mapped_column(String, index=True)
    name: Mapped[str | None] = mapped_column(String)
    age: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gender: Mapped[str | None] = mapped_column(String)
    last_seen_date: Mapped[str | None] = mapped_column(String)
    last_seen_location: Mapped[str | None] = mapped_column(String, nullable=True)
    district: Mapped[str | None] = mapped_column(String, index=True)
    risk_tier: Mapped[str | None] = mapped_column(String, index=True)
    status: Mapped[str | None] = mapped_column(String, index=True)
    repeat_count: Mapped[int | None] = mapped_column(Integer)

    COLS = ["mp_id", "fir_number", "name", "age", "gender", "last_seen_date",
            "last_seen_location", "district", "risk_tier", "status", "repeat_count"]

    def as_dict(self) -> dict:
        return {c: getattr(self, c) for c in self.COLS}
