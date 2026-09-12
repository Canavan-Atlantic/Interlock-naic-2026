"""Initial project portfolio schema."""

from sqlalchemy.engine import Connection

from ..models import Base


def upgrade(connection: Connection) -> None:
    """Create the initial schema for a fresh database."""

    Base.metadata.create_all(connection)
