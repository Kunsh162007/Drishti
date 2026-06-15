"""ORM models mirroring the canonical schema in SPEC.md."""
from sqlalchemy import Column, Integer, Float, String, Text, Boolean, Index
from .db import Base


def _as_dict(obj, cols):
    return {c: getattr(obj, c) for c in cols}


class Crime(Base):
    __tablename__ = "crimes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fir_number = Column(String, unique=True, index=True)
    district = Column(String, index=True)
    police_station = Column(String, index=True)
    crime_type = Column(String, index=True)
    crime_category = Column(String, index=True)
    severity = Column(Integer)
    latitude = Column(Float)
    longitude = Column(Float)
    h3_r7 = Column(String, index=True)
    h3_r8 = Column(String, index=True)
    h3_r9 = Column(String, index=True)
    occurred_at = Column(String, index=True)
    reported_at = Column(String)
    hour = Column(Integer, index=True)
    day_of_week = Column(Integer)
    modus_operandi = Column(Text)
    description = Column(Text)
    status = Column(String, index=True)
    victim_count = Column(Integer)
    accused_count = Column(Integer)
    property_value_inr = Column(Float, nullable=True)
    weapon_used = Column(String, nullable=True)
    source = Column(String)

    COLS = ["fir_number", "district", "police_station", "crime_type", "crime_category",
            "severity", "latitude", "longitude", "h3_r7", "h3_r8", "h3_r9", "occurred_at",
            "reported_at", "hour", "day_of_week", "modus_operandi", "description", "status",
            "victim_count", "accused_count", "property_value_inr", "weapon_used", "source"]

    def as_dict(self):
        return _as_dict(self, self.COLS)


class Person(Base):
    __tablename__ = "persons"
    id = Column(Integer, primary_key=True, autoincrement=True)
    person_id = Column(String, index=True)
    fir_number = Column(String, index=True)
    full_name = Column(String, index=True)
    normalized_name = Column(String, index=True)
    role = Column(String, index=True)
    gender = Column(String)
    age = Column(Integer, nullable=True)
    phone = Column(String, nullable=True, index=True)
    address = Column(String, nullable=True)
    district = Column(String)
    true_identity_id = Column(String, index=True)

    COLS = ["person_id", "fir_number", "full_name", "normalized_name", "role", "gender",
            "age", "phone", "address", "district", "true_identity_id"]

    def as_dict(self):
        return _as_dict(self, self.COLS)


class Vehicle(Base):
    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    vehicle_id = Column(String, index=True)
    fir_number = Column(String, index=True)
    reg_number = Column(String, index=True)
    vehicle_type = Column(String)
    make_color = Column(String, nullable=True)

    COLS = ["vehicle_id", "fir_number", "reg_number", "vehicle_type", "make_color"]

    def as_dict(self):
        return _as_dict(self, self.COLS)


Index("ix_crimes_type_date", Crime.crime_type, Crime.occurred_at)


class CDR(Base):
    """Call Detail Records (telecom metadata for lawful link analysis)."""
    __tablename__ = "cdr"
    id = Column(Integer, primary_key=True, autoincrement=True)
    cdr_id = Column(String, index=True)
    caller_msisdn = Column(String, index=True)
    callee_msisdn = Column(String, index=True)
    start_time = Column(String, index=True)
    duration_sec = Column(Integer)
    cell_tower_id = Column(String, index=True)
    tower_lat = Column(Float)
    tower_lng = Column(Float)
    call_type = Column(String)

    COLS = ["cdr_id", "caller_msisdn", "callee_msisdn", "start_time", "duration_sec",
            "cell_tower_id", "tower_lat", "tower_lng", "call_type"]

    def as_dict(self):
        return _as_dict(self, self.COLS)


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String, index=True)
    holder_name = Column(String)
    bank = Column(String)
    district = Column(String)
    is_mule = Column(Boolean)

    COLS = ["account_id", "holder_name", "bank", "district", "is_mule"]

    def as_dict(self):
        return _as_dict(self, self.COLS)


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    txn_id = Column(String, index=True)
    from_account = Column(String, index=True)
    to_account = Column(String, index=True)
    amount_inr = Column(Float)
    timestamp = Column(String, index=True)
    channel = Column(String)
    fir_number = Column(String, index=True, nullable=True)
    is_flagged = Column(Boolean)

    COLS = ["txn_id", "from_account", "to_account", "amount_inr", "timestamp",
            "channel", "fir_number", "is_flagged"]

    def as_dict(self):
        return _as_dict(self, self.COLS)


class MissingPerson(Base):
    __tablename__ = "missing_persons"
    id = Column(Integer, primary_key=True, autoincrement=True)
    mp_id = Column(String, index=True)
    fir_number = Column(String, index=True)
    name = Column(String)
    age = Column(Integer, nullable=True)
    gender = Column(String)
    last_seen_date = Column(String)
    last_seen_location = Column(String, nullable=True)
    district = Column(String, index=True)
    risk_tier = Column(String, index=True)
    status = Column(String, index=True)
    repeat_count = Column(Integer)

    COLS = ["mp_id", "fir_number", "name", "age", "gender", "last_seen_date",
            "last_seen_location", "district", "risk_tier", "status", "repeat_count"]

    def as_dict(self):
        return _as_dict(self, self.COLS)


class AuditLog(Base):
    """Append-only, hash-chained tamper-evident audit ledger (see backend/audit.py)."""
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    seq = Column(Integer, index=True)
    ts = Column(String)
    user = Column(String)
    action = Column(String)
    resource = Column(String)
    detail = Column(String)
    prev_hash = Column(String)
    entry_hash = Column(String)

    COLS = ["seq", "ts", "user", "action", "resource", "detail", "prev_hash", "entry_hash"]

    def as_dict(self):
        return _as_dict(self, self.COLS)
