"""SQLAlchemy engine/session. SQLite by default; set DATABASE_URL to use Postgres in production."""
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

from . import config

_is_sqlite = config.DATABASE_URL.startswith("sqlite")
connect_args = {"check_same_thread": False} if _is_sqlite else {}
engine = create_engine(config.DATABASE_URL, connect_args=connect_args, future=True)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")   # concurrent reads during writes
        cur.execute("PRAGMA synchronous=NORMAL") # safe + faster than FULL
        cur.execute("PRAGMA busy_timeout=10000") # wait up to 10 s on lock
        cur.execute("PRAGMA cache_size=-32000")  # 32 MB page cache
        cur.close()

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_session():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
