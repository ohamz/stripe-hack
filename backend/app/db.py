from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = get_settings().database_url
        _engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _fk_on(dbapi_conn, _):  # noqa: ANN001
                dbapi_conn.execute("PRAGMA foreign_keys=ON")
    return _engine


def set_engine(engine) -> None:  # used by tests
    global _engine
    _engine = engine


def init_db() -> None:
    from app import models  # noqa: F401  (registers tables)

    SQLModel.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator[Session]:
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session


def get_session() -> Iterator[Session]:  # FastAPI dependency
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session
