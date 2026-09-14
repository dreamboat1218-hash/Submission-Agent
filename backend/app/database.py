from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_session_factory: sessionmaker | None = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        kwargs = {}
        if settings.database_url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(settings.database_url, pool_pre_ping=True, **kwargs)
    return _engine


def get_session_factory() -> sessionmaker:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)
    return _session_factory


def init_db() -> None:
    from . import models  # noqa: F401
    from .seed import seed_data

    Base.metadata.create_all(get_engine())
    _ensure_schema_upgrades(get_engine())
    with get_session_factory()() as db:
        seed_data(db)


def _ensure_schema_upgrades(engine) -> None:
    """轻量迁移：为已有 tasks 表补充新增列，避免 create_all 不修改旧表。"""
    columns = {column["name"] for column in inspect(engine).get_columns("tasks")}
    if "source" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN source VARCHAR(20) NOT NULL DEFAULT 'workbench'"))


def get_db() -> Generator[Session, None, None]:
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
