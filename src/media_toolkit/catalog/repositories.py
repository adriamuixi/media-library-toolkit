"""Catalog repositories for libraries and media sources."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


@dataclass(frozen=True)
class LibraryRecord:
    """A logical media library stored in the catalog."""

    library_id: str
    name: str
    environment: str
    description: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class SourceRecord:
    """A named provenance source within a logical library."""

    source_id: str
    library_id: str
    library_name: str
    name: str
    source_type: str
    default_timezone: str | None
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RegistrationResult:
    """The result of an idempotent catalog registration."""

    record: LibraryRecord | SourceRecord
    created: bool


def _clean_required(value: str, label: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise CatalogError(f"{label} cannot be empty.")
    return cleaned


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


def _validate_timezone(value: str | None) -> str | None:
    timezone = _clean_optional(value)
    if timezone is None:
        return None
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError as exc:
        raise CatalogError(f"Unknown IANA timezone: {timezone}") from exc
    return timezone


def _library_from_row(row: sqlite3.Row) -> LibraryRecord:
    return LibraryRecord(
        library_id=row["library_id"],
        name=row["name"],
        environment=row["environment"],
        description=row["description"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _source_from_row(row: sqlite3.Row) -> SourceRecord:
    return SourceRecord(
        source_id=row["source_id"],
        library_id=row["library_id"],
        library_name=row["library_name"],
        name=row["name"],
        source_type=row["source_type"],
        default_timezone=row["default_timezone"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def register_library(
    database: Path,
    environment: str,
    name: str,
    description: str | None = None,
) -> RegistrationResult:
    """Create a library or return an identical existing registration."""
    require_database(database, environment)
    clean_name = _clean_required(name, "Library name")
    clean_description = _clean_optional(description)
    normalized_environment = environment.upper()

    with open_database(database) as connection:
        existing = connection.execute(
            """
            SELECT library_id, name, environment, description, created_at, updated_at
            FROM library
            WHERE name = ? COLLATE NOCASE AND environment = ?
            """,
            (clean_name, normalized_environment),
        ).fetchone()
        if existing is not None:
            record = _library_from_row(existing)
            if record.description != clean_description:
                raise CatalogError(
                    f"Library '{record.name}' already exists with a different description."
                )
            return RegistrationResult(record=record, created=False)

        timestamp = datetime.now(UTC).isoformat()
        library_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO library (
                library_id, name, environment, description, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                library_id,
                clean_name,
                normalized_environment,
                clean_description,
                timestamp,
                timestamp,
            ),
        )
        row = connection.execute(
            """
            SELECT library_id, name, environment, description, created_at, updated_at
            FROM library WHERE library_id = ?
            """,
            (library_id,),
        ).fetchone()
    return RegistrationResult(record=_library_from_row(row), created=True)


def list_libraries(database: Path, environment: str) -> list[LibraryRecord]:
    """List libraries in deterministic name order."""
    require_database(database, environment)
    with open_database(database) as connection:
        rows = connection.execute(
            """
            SELECT library_id, name, environment, description, created_at, updated_at
            FROM library
            WHERE environment = ?
            ORDER BY name COLLATE NOCASE, library_id
            """,
            (environment.upper(),),
        ).fetchall()
    return [_library_from_row(row) for row in rows]


def register_source(
    database: Path,
    environment: str,
    library_name: str,
    name: str,
    source_type: str,
    default_timezone: str | None = None,
) -> RegistrationResult:
    """Create a source or return an identical existing registration."""
    require_database(database, environment)
    clean_library_name = _clean_required(library_name, "Library name")
    clean_name = _clean_required(name, "Source name")
    clean_source_type = _clean_required(source_type, "Source type").upper()
    clean_timezone = _validate_timezone(default_timezone)
    normalized_environment = environment.upper()

    with open_database(database) as connection:
        library = connection.execute(
            """
            SELECT library_id, name
            FROM library
            WHERE name = ? COLLATE NOCASE AND environment = ?
            """,
            (clean_library_name, normalized_environment),
        ).fetchone()
        if library is None:
            raise CatalogError(
                f"Library '{clean_library_name}' does not exist in the selected profile."
            )

        existing = connection.execute(
            """
            SELECT
                s.source_id,
                s.library_id,
                l.name AS library_name,
                s.name,
                s.source_type,
                s.default_timezone,
                s.created_at,
                s.updated_at
            FROM source AS s
            JOIN library AS l ON l.library_id = s.library_id
            WHERE s.library_id = ? AND s.name = ? COLLATE NOCASE
            """,
            (library["library_id"], clean_name),
        ).fetchone()
        if existing is not None:
            record = _source_from_row(existing)
            if (
                record.source_type != clean_source_type
                or record.default_timezone != clean_timezone
            ):
                raise CatalogError(
                    f"Source '{record.name}' already exists with different settings."
                )
            return RegistrationResult(record=record, created=False)

        timestamp = datetime.now(UTC).isoformat()
        source_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO source (
                source_id,
                library_id,
                name,
                source_type,
                default_timezone,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_id,
                library["library_id"],
                clean_name,
                clean_source_type,
                clean_timezone,
                timestamp,
                timestamp,
            ),
        )
        row = connection.execute(
            """
            SELECT
                s.source_id,
                s.library_id,
                l.name AS library_name,
                s.name,
                s.source_type,
                s.default_timezone,
                s.created_at,
                s.updated_at
            FROM source AS s
            JOIN library AS l ON l.library_id = s.library_id
            WHERE s.source_id = ?
            """,
            (source_id,),
        ).fetchone()
    return RegistrationResult(record=_source_from_row(row), created=True)


def list_sources(
    database: Path,
    environment: str,
    library_name: str | None = None,
) -> list[SourceRecord]:
    """List sources, optionally restricted to one named library."""
    require_database(database, environment)
    parameters: list[str] = [environment.upper()]
    library_filter = ""
    if library_name is not None:
        library_filter = " AND l.name = ? COLLATE NOCASE"
        parameters.append(_clean_required(library_name, "Library name"))

    with open_database(database) as connection:
        rows = connection.execute(
            f"""
            SELECT
                s.source_id,
                s.library_id,
                l.name AS library_name,
                s.name,
                s.source_type,
                s.default_timezone,
                s.created_at,
                s.updated_at
            FROM source AS s
            JOIN library AS l ON l.library_id = s.library_id
            WHERE l.environment = ?{library_filter}
            ORDER BY l.name COLLATE NOCASE, s.name COLLATE NOCASE, s.source_id
            """,
            parameters,
        ).fetchall()
    return [_source_from_row(row) for row in rows]
