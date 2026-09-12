"""Pytest-wide database isolation for application integration tests."""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path
from typing import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url


_TEST_DATABASE_NAME = os.getenv("INTERLOCK_TEST_DATABASE_NAME", "interlock_test")
_TEMPORARY_SQLITE_PATH: Path | None = None


def _is_postgresql(url: URL) -> bool:
    return url.get_backend_name() in {"postgres", "postgresql"}


def _database_identity(url: URL) -> tuple[str | None, int | None, str | None, str | None]:
    """Return connection identity without including the password."""

    return url.host, url.port, url.username, url.database


def _ensure_postgresql_database(test_url: URL) -> None:
    """Create the isolated database if the configured PostgreSQL server lacks it."""

    database_name = test_url.database
    if not database_name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database_name):
        raise RuntimeError("INTERLOCK test database name must be a simple PostgreSQL identifier")

    admin_engine = create_engine(
        test_url.set(database="postgres"),
        future=True,
        pool_pre_ping=True,
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin_engine.connect() as connection:
            exists = connection.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :database_name"),
                {"database_name": database_name},
            ).scalar()
            if not exists:
                connection.exec_driver_sql(f'CREATE DATABASE "{database_name}"')
    except Exception:
        # Keep credentials and complete connection URLs out of pytest output.
        raise RuntimeError("Could not prepare the isolated PostgreSQL test database") from None
    finally:
        admin_engine.dispose()


def _configure_isolated_database() -> None:
    """Set DATABASE_URL before any test module imports the backend DB layer."""

    global _TEMPORARY_SQLITE_PATH

    configured_test_url = os.getenv("INTERLOCK_TEST_DATABASE_URL")
    configured_database_url = os.getenv("DATABASE_URL") or os.getenv("INTERLOCK_DATABASE_URL")

    if configured_test_url:
        test_url = make_url(configured_test_url)
        if configured_database_url and _is_postgresql(test_url):
            configured_url = make_url(configured_database_url)
            if _is_postgresql(configured_url) and _database_identity(test_url) == _database_identity(configured_url):
                raise RuntimeError("INTERLOCK_TEST_DATABASE_URL must not equal the development DATABASE_URL")
    elif configured_database_url and _is_postgresql(make_url(configured_database_url)):
        configured_url = make_url(configured_database_url)
        test_url = configured_url.set(database=_TEST_DATABASE_NAME)
        if _database_identity(test_url) == _database_identity(configured_url) and configured_url.database != _TEST_DATABASE_NAME:
            raise RuntimeError("The isolated PostgreSQL test database must differ from the development database")
    else:
        temporary_file = tempfile.NamedTemporaryFile(
            prefix="interlock-pytest-", suffix=".sqlite3", delete=False
        )
        temporary_file.close()
        _TEMPORARY_SQLITE_PATH = Path(temporary_file.name)
        test_url = make_url(f"sqlite+pysqlite:///{_TEMPORARY_SQLITE_PATH.as_posix()}")

    if _is_postgresql(test_url):
        _ensure_postgresql_database(test_url)

    # backend.app.db.database.database_url() checks DATABASE_URL first. This
    # assignment therefore happens before backend application imports run.
    os.environ["DATABASE_URL"] = test_url.render_as_string(hide_password=False)


_configure_isolated_database()


def _clear_database() -> None:
    """Remove only test rows, in FK-safe order, from the isolated database."""

    from backend.app.db import session_scope
    from backend.app.db.models import AssessmentRun, Project

    with session_scope() as session:
        session.query(AssessmentRun).delete(synchronize_session=False)
        session.query(Project).delete(synchronize_session=False)
        session.commit()


@pytest.fixture(scope="session", autouse=True)
def isolated_database() -> Iterator[None]:
    """Create the schema once and make it available to every test."""

    from backend.app.db import init_db

    init_db()
    yield


@pytest.fixture(autouse=True)
def clean_database(isolated_database: None) -> Iterator[None]:
    """Give every test a clean database and leave no test rows behind."""

    _clear_database()
    yield
    _clear_database()


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Dispose the temporary SQLite engine and remove only its temp file."""

    del session, exitstatus
    if _TEMPORARY_SQLITE_PATH is None:
        return
    try:
        from backend.app.db import get_engine

        get_engine().dispose()
    except Exception:
        pass
    _TEMPORARY_SQLITE_PATH.unlink(missing_ok=True)
