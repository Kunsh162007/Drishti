"""Seed the PRODUCTION database (DATABASE_URL) from the shared demo CSVs.

Works against Postgres or SQLite (whatever DATABASE_URL points to). Run from production/:
    python scripts/seed_prod.py
"""
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]   # repo root
PROD = Path(__file__).resolve().parents[1]   # production/
sys.path.insert(0, str(PROD))

from app.db import create_all, SessionLocal                                              # noqa: E402
from app.models import Crime, Person, Vehicle, CDR, Account, Transaction, MissingPerson  # noqa: E402

SEED = ROOT / "demo" / "data" / "seed"


def _coerce(v):
    if v is None:
        return None
    return v.item() if hasattr(v, "item") else v


def _load(model, csv_path):
    if not csv_path.exists():
        print(f"  ! missing {csv_path.name} — skipped")
        return 0
    df = pd.read_csv(csv_path).where(lambda d: pd.notna(d), None)
    cols = [c for c in model.COLS if c in df.columns]
    rows = [model(**{c: _coerce(r[c]) for c in cols}) for _, r in df.iterrows()]
    db = SessionLocal()
    db.bulk_save_objects(rows)
    db.commit()
    db.close()
    return len(rows)


def main():
    create_all()
    counts = {
        "crimes": _load(Crime, SEED / "crimes.csv"),
        "persons": _load(Person, SEED / "persons.csv"),
        "vehicles": _load(Vehicle, SEED / "vehicles.csv"),
        "cdr": _load(CDR, SEED / "cdr.csv"),
        "accounts": _load(Account, SEED / "accounts.csv"),
        "transactions": _load(Transaction, SEED / "transactions.csv"),
        "missing_persons": _load(MissingPerson, SEED / "missing_persons.csv"),
    }
    print("Seeded: " + ", ".join(f"{v} {k}" for k, v in counts.items()))


if __name__ == "__main__":
    main()
