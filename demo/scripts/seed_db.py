"""Load the generated seed CSVs (demo/data/seed/*.csv) into the database.

Run after generate_data.py + generate_extended_data.py:
    python demo/scripts/seed_db.py
Idempotent: drops and recreates the demo tables, then bulk-inserts.
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]   # repo root
sys.path.insert(0, str(ROOT))

from demo.backend.db import Base, engine, SessionLocal                                  # noqa: E402
from demo.backend.models import (Crime, Person, Vehicle, CDR, Account, Transaction,      # noqa: E402
                                 MissingPerson)
from demo.backend.config import SEED_DIR                                                # noqa: E402


def _coerce(v):
    if v is None:
        return None
    if hasattr(v, "item"):          # numpy scalar -> python native
        try:
            return v.item()
        except Exception:
            return v
    return v


def _load(model, csv_path):
    if not csv_path.exists():
        print(f"  ! missing {csv_path.name} — skipped")
        return 0
    df = pd.read_csv(csv_path)
    df = df.where(pd.notna(df), None)
    cols = [c for c in model.COLS if c in df.columns]
    rows = [model(**{c: _coerce(r[c]) for c in cols}) for _, r in df.iterrows()]
    db = SessionLocal()
    db.bulk_save_objects(rows)
    db.commit()
    db.close()
    return len(rows)


def main():
    print("Recreating tables...")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    print("Loading seed data from", SEED_DIR)
    counts = {
        "crimes": _load(Crime, SEED_DIR / "crimes.csv"),
        "persons": _load(Person, SEED_DIR / "persons.csv"),
        "vehicles": _load(Vehicle, SEED_DIR / "vehicles.csv"),
        "cdr": _load(CDR, SEED_DIR / "cdr.csv"),
        "accounts": _load(Account, SEED_DIR / "accounts.csv"),
        "transactions": _load(Transaction, SEED_DIR / "transactions.csv"),
        "missing_persons": _load(MissingPerson, SEED_DIR / "missing_persons.csv"),
    }
    print("Seeded: " + ", ".join(f"{v} {k}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
