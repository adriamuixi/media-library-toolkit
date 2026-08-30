"""Read-only streaming SHA-256 orchestration and catalog persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import logging
from pathlib import Path
import sqlite3
from uuid import uuid4

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError
from media_toolkit.scan.safety import (
    ensure_external_working_paths,
    resolve_cataloged_file,
    resolve_media_root,
)


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class HashRequest:
    """Validated inputs for one read-only hashing run."""

    database: Path
    environment: str
    library_name: str
    source_name: str
    root: Path
    media_filter: str
    batch_size: int
    chunk_size_bytes: int
    generated_paths: tuple[Path, ...]
    force: bool = False


@dataclass(frozen=True)
class HashSummary:
    """Counts produced by a hashing run."""

    selected_count: int
    hashed_count: int
    cached_count: int
    error_count: int
    bytes_hashed: int


@dataclass(frozen=True)
class HashRecord:
    """Current hash result rendered for inspection."""

    relative_path: str
    media_type: str
    size_bytes: int
    digest: str
    finished_at: str


def stream_sha256(path: Path, chunk_size_bytes: int) -> tuple[str, int]:
    """Hash one file using bounded reads and return digest plus byte count."""
    digest = sha256()
    bytes_hashed = 0
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size_bytes):
            digest.update(chunk)
            bytes_hashed += len(chunk)
    return digest.hexdigest(), bytes_hashed


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _selected_types(media_filter: str) -> tuple[str, ...]:
    if media_filter == "photos":
        return ("PHOTO",)
    if media_filter == "videos":
        return ("VIDEO",)
    if media_filter == "all":
        return ("PHOTO", "VIDEO", "SIDECAR", "UNKNOWN")
    raise CatalogError(f"Unsupported hash media filter: {media_filter}.")


def _source_id(
    connection: sqlite3.Connection,
    environment: str,
    library_name: str,
    source_name: str,
) -> str:
    row = connection.execute(
        """
        SELECT s.source_id
        FROM source AS s
        JOIN library AS l ON l.library_id = s.library_id
        WHERE l.environment = ?
          AND l.name = ? COLLATE NOCASE
          AND s.name = ? COLLATE NOCASE
        """,
        (environment.upper(), library_name.strip(), source_name.strip()),
    ).fetchone()
    if row is None:
        raise CatalogError(
            f"Source '{source_name}' does not exist in library '{library_name}'."
        )
    return str(row["source_id"])


def _is_cached(connection: sqlite3.Connection, row: sqlite3.Row) -> bool:
    cached = connection.execute(
        """
        SELECT 1
        FROM media_hash AS current
        JOIN hash_attempt AS attempt ON attempt.hash_id = current.hash_id
        WHERE current.media_id = ? AND attempt.algorithm = 'SHA256'
          AND attempt.status = 'SUCCESS'
          AND attempt.input_size_bytes = ? AND attempt.input_modified_time_ns = ?
        LIMIT 1
        """,
        (row["media_id"], row["size_bytes"], row["modified_time_ns"]),
    ).fetchone()
    return cached is not None


def _record_error(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    started_at: str,
    error: Exception,
) -> None:
    connection.execute(
        """
        INSERT INTO hash_attempt (
            hash_id, media_id, location_id, algorithm, status,
            input_size_bytes, input_modified_time_ns, bytes_hashed,
            started_at, finished_at, error_type, error_message
        ) VALUES (?, ?, ?, 'SHA256', 'ERROR', ?, ?, 0, ?, ?, ?, ?)
        """,
        (
            str(uuid4()), row["media_id"], row["location_id"],
            row["size_bytes"], row["modified_time_ns"], started_at, _now(),
            type(error).__name__.upper(), str(error),
        ),
    )


def _record_success(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    started_at: str,
    digest: str,
    bytes_hashed: int,
) -> None:
    hash_id = str(uuid4())
    timestamp = _now()
    connection.execute(
        """
        INSERT INTO hash_attempt (
            hash_id, media_id, location_id, algorithm, status, digest,
            input_size_bytes, input_modified_time_ns, bytes_hashed,
            started_at, finished_at
        ) VALUES (?, ?, ?, 'SHA256', 'SUCCESS', ?, ?, ?, ?, ?, ?)
        """,
        (
            hash_id, row["media_id"], row["location_id"], digest,
            row["size_bytes"], row["modified_time_ns"], bytes_hashed,
            started_at, timestamp,
        ),
    )
    connection.execute(
        """
        INSERT INTO media_hash (media_id, hash_id, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(media_id) DO UPDATE SET
            hash_id = excluded.hash_id,
            updated_at = excluded.updated_at
        """,
        (row["media_id"], hash_id, timestamp),
    )


def run_hashing(request: HashRequest) -> HashSummary:
    """Hash selected cataloged files without modifying their content or metadata."""
    require_database(request.database, request.environment)
    root = resolve_media_root(request.root)
    ensure_external_working_paths(root, request.generated_paths)
    types = _selected_types(request.media_filter)
    hashed = cached = errors = total_bytes = pending = 0
    with open_database(request.database) as connection:
        source_id = _source_id(
            connection, request.environment, request.library_name, request.source_name
        )
        placeholders = ", ".join("?" for _ in types)
        rows = connection.execute(
            f"""
            SELECT fl.location_id, fl.media_id, fl.relative_path,
                   fl.size_bytes, fl.modified_time_ns, mf.media_type
            FROM file_location AS fl
            JOIN media_file AS mf ON mf.media_id = fl.media_id
            WHERE fl.source_id = ? AND fl.present = 1 AND mf.status = 'PRESENT'
              AND mf.media_type IN ({placeholders})
            ORDER BY fl.normalized_relative_path, fl.relative_path
            """,
            (source_id, *types),
        ).fetchall()
        for row in rows:
            if not request.force and _is_cached(connection, row):
                cached += 1
                continue
            started_at = _now()
            try:
                path = resolve_cataloged_file(root, row["relative_path"])
                before = path.stat()
                if (
                    before.st_size != row["size_bytes"]
                    or before.st_mtime_ns != row["modified_time_ns"]
                ):
                    raise CatalogError(
                        "File size or modification time changed after inventory; run scan again."
                    )
                digest, byte_count = stream_sha256(path, request.chunk_size_bytes)
                after = path.stat()
                if (
                    after.st_size != before.st_size
                    or after.st_mtime_ns != before.st_mtime_ns
                ):
                    raise CatalogError("File changed during hashing; the digest was discarded.")
                if byte_count != before.st_size:
                    raise CatalogError("Hashed byte count does not match the cataloged file size.")
                _record_success(connection, row, started_at, digest, byte_count)
                hashed += 1
                total_bytes += byte_count
            except Exception as exc:
                _record_error(connection, row, started_at, exc)
                LOGGER.warning("Hashing failed path=%s error=%s", row["relative_path"], exc)
                errors += 1
            pending += 1
            if pending >= request.batch_size:
                connection.commit()
                pending = 0
        connection.commit()
    return HashSummary(len(rows), hashed, cached, errors, total_bytes)


def list_hashes(
    database: Path,
    environment: str,
    library_name: str,
    source_name: str,
) -> list[HashRecord]:
    """List current SHA-256 values in deterministic source path order."""
    require_database(database, environment)
    with open_database(database) as connection:
        source_id = _source_id(connection, environment, library_name, source_name)
        rows = connection.execute(
            """
            SELECT fl.relative_path, mf.media_type, fl.size_bytes,
                   attempt.digest, attempt.finished_at
            FROM media_hash AS current
            JOIN hash_attempt AS attempt ON attempt.hash_id = current.hash_id
            JOIN media_file AS mf ON mf.media_id = current.media_id
            JOIN file_location AS fl ON fl.media_id = current.media_id
            WHERE fl.source_id = ?
            ORDER BY fl.normalized_relative_path, fl.relative_path
            """,
            (source_id,),
        ).fetchall()
    return [
        HashRecord(
            row["relative_path"], row["media_type"], row["size_bytes"],
            row["digest"], row["finished_at"],
        )
        for row in rows
    ]
