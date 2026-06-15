"""SQLAlchemy 2.x engine/session factory.

Targets PostgreSQL/PostGIS in production (DATABASE_URL=postgresql+psycopg://...)
but transparently works with SQLite for local import/compile checks. DB I/O is
done in the API layer; analytics functions stay pure (records in -> results out).
"""
from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.DATABASE_URL
    connect_args = {}
    kwargs = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        # SQLite has no real pool; drop pool sizing kwargs.
    else:
        kwargs.update(pool_size=10, max_overflow=20)
    return create_engine(url, connect_args=connect_args, **kwargs)


engine = _make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_session() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all() -> None:
    """Create tables if they do not exist. Models must be imported first."""
    from . import models  # noqa: F401  (register mappers)

    Base.metadata.create_all(bind=engine)
