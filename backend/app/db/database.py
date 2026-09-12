"""Database configuration and a deliberately small migration runner."""

from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from threading import RLock
from typing import Iterator

from sqlalchemy import Column, DateTime, MetaData, String, Table, create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from .models import Base


DEFAULT_DATABASE_URL = "sqlite+pysqlite:///:memory:"
MIGRATION_VERSION = "0001_initial"

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None
_configured_url: str | None = None
_initialized_engine: Engine | None = None
_migration_lock = RLock()

_migration_metadata = MetaData()
_schema_migrations = Table(
    "schema_migrations",
    _migration_metadata,
    Column("version", String(64), primary_key=True),
    Column("applied_at", DateTime(timezone=True), nullable=False),
)


def database_url() -> str:
    """Return the configured URL without ever logging its value."""

    return os.getenv("DATABASE_URL") or os.getenv("INTERLOCK_DATABASE_URL") or DEFAULT_DATABASE_URL


def configure_database(url: str) -> Engine:
    """Configure a new engine, primarily useful for isolated tests."""

    global _engine, _session_factory, _configured_url, _initialized_engine
    if _engine is not None:
        _engine.dispose()
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine_kwargs: dict[str, object] = {"future": True, "pool_pre_ping": True}
    if url.startswith("sqlite") and ":memory:" in url:
        engine_kwargs["poolclass"] = StaticPool
    _engine = create_engine(url, connect_args=connect_args, **engine_kwargs)
    _session_factory = sessionmaker(bind=_engine, expire_on_commit=False, future=True)
    _configured_url = url
    _initialized_engine = None
    return _engine


def get_engine() -> Engine:
    """Lazily configure the engine from the process environment."""

    configured = database_url()
    if _engine is None or _configured_url != configured:
        return configure_database(configured)
    return _engine


def init_db() -> None:
    """Apply pending migrations once for the current engine."""

    global _initialized_engine
    engine = get_engine()
    with _migration_lock:
        if _initialized_engine is engine:
            return
        with engine.begin() as connection:
            _migration_metadata.create_all(connection, checkfirst=True)
            applied = set(connection.execute(select(_schema_migrations.c.version)).scalars())
            if MIGRATION_VERSION not in applied:
                migration = importlib.import_module(".migrations.0001_initial", package=__package__)
                migration.upgrade(connection)
                from datetime import datetime, timezone

                connection.execute(
                    _schema_migrations.insert().values(
                        version=MIGRATION_VERSION,
                        applied_at=datetime.now(timezone.utc),
                    )
                )
        _initialized_engine = engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Yield a transaction-scoped session and roll back on any failure."""

    init_db()
    if _session_factory is None:  # pragma: no cover - guarded by init_db
        raise RuntimeError("Database session factory is unavailable")
    session = _session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
