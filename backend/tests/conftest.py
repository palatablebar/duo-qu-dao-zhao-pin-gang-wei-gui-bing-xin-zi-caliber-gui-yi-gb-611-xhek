"""共享测试夹具：内存 SQLite + 真实 seed 数据（服务层端到端）。"""
from __future__ import annotations

import os

os.environ.setdefault("DB_KIND", "sqlite")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


@pytest.fixture(scope="session")
def engine():
    from src.models import Base

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(engine):
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection, autoflush=False, expire_on_commit=False)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
