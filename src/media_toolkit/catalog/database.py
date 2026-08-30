"""SQLite connection, initialization, and safe test reset operations."""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from uuid import uuid4

from media_toolkit.catalog.migration_runner import apply_migrations
from media_toolkit.errors import DatabaseSafetyError


@dataclass(frozen=True)
class DatabaseStatus:
    """Human-readable catalog identity and migration state."""

    path: Path
    exists: bool
    database_id: str | None = None
    profile_name: str | None = None
    environment: str | None = None
    schema_version: int | None = None


def connect_database(path: Path) -> sqlite3.Connection:
    """Open a catalog connection with required safety pragmas."""
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = FULL")
    return connection


@contextmanager
def open_database(path: Path) -> Generator[sqlite3.Connection, None, None]:
    """Open a transactional connection and always close it on exit."""
    connection = connect_database(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database(path: Path, profile_name: str, environment: str) -> DatabaseStatus:
    """Create or migrate a catalog and validate its environment marker."""
    normalized_environment = environment.upper()
    existed_before_initialization = path.is_file()
    if existed_before_initialization:
        existing_status = get_database_status(path)
        if existing_status.environment != normalized_environment:
            raise DatabaseSafetyError(
                "Database environment marker does not match the selected profile: "
                f"database={existing_status.environment}, profile={normalized_environment}."
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    with open_database(path) as connection:
        apply_migrations(connection)
        row = connection.execute(
            "SELECT database_id, profile_name, environment FROM catalog_metadata WHERE singleton = 1"
        ).fetchone()
        if row is None:
            connection.execute(
                """
                INSERT INTO catalog_metadata (
                    singleton, database_id, profile_name, environment, created_at
                ) VALUES (1, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    profile_name,
                    normalized_environment,
                    datetime.now(UTC).isoformat(),
                ),
            )
        elif row["environment"] != normalized_environment:
            raise DatabaseSafetyError(
                "Database environment marker does not match the selected profile: "
                f"database={row['environment']}, profile={normalized_environment}."
            )
    return get_database_status(path)


def get_database_status(path: Path) -> DatabaseStatus:
    """Inspect a catalog without creating it."""
    if not path.is_file():
        return DatabaseStatus(path=path, exists=False)
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            metadata = connection.execute(
                "SELECT database_id, profile_name, environment FROM catalog_metadata WHERE singleton = 1"
            ).fetchone()
            version_row = connection.execute(
                "SELECT COALESCE(MAX(version), 0) AS version FROM schema_version"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        raise DatabaseSafetyError(f"The file is not a valid toolkit catalog: {path}") from exc

    if metadata is None:
        raise DatabaseSafetyError(f"Catalog metadata marker is missing: {path}")
    return DatabaseStatus(
        path=path,
        exists=True,
        database_id=metadata["database_id"],
        profile_name=metadata["profile_name"],
        environment=metadata["environment"],
        schema_version=int(version_row["version"]),
    )


def require_database(path: Path, expected_environment: str) -> DatabaseStatus:
    """Require an initialized catalog with the expected environment marker."""
    status = get_database_status(path)
    if not status.exists:
        raise DatabaseSafetyError(
            f"Catalog is not initialized: {path}. Run 'media init' first."
        )
    normalized_environment = expected_environment.upper()
    if status.environment != normalized_environment:
        raise DatabaseSafetyError(
            "Database environment marker does not match the selected profile: "
            f"database={status.environment}, profile={normalized_environment}."
        )
    return status


def reset_test_database(path: Path, profile_name: str, environment: str) -> DatabaseStatus:
    """Delete and recreate a catalog only when both profile and database are TEST."""
    if environment.upper() != "TEST":
        raise DatabaseSafetyError("Database reset is restricted to TEST profiles.")

    status = get_database_status(path)
    if status.exists and status.environment != "TEST":
        raise DatabaseSafetyError(
            "Refusing to reset a database that is not marked as TEST."
        )

    if status.exists:
        path.unlink()
        for suffix in ("-wal", "-shm"):
            auxiliary = Path(f"{path}{suffix}")
            if auxiliary.exists():
                auxiliary.unlink()

    return initialize_database(path, profile_name, environment)
