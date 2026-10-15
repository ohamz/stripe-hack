import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app import db
from app import models  # noqa: F401


@pytest.fixture()
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    previous = db._engine
    db.set_engine(engine)
    with Session(engine, expire_on_commit=False) as s:
        yield s
    db.set_engine(previous)
