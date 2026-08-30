"""Size-based candidate generation for later exact duplicate comparison."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


@dataclass(frozen=True)
class SizeCandidateMember:
    """One present file that shares its byte size with another file."""

    media_id: str
    source_name: str
    relative_path: str
    media_type: str
    size_bytes: int
    sha256: str | None


@dataclass(frozen=True)
class SizeCandidateGroup:
    """A same-size group requiring SHA-256 comparison before any conclusion."""

    size_bytes: int
    members: tuple[SizeCandidateMember, ...]


@dataclass(frozen=True)
class ExactDuplicateMember:
    """One present cataloged file in an exact SHA-256 content group."""

    media_id: str
    source_name: str
    relative_path: str
    media_type: str
    size_bytes: int


@dataclass(frozen=True)
class ExactDuplicateGroup:
    """A group of present files with the same current SHA-256 digest."""

    sha256: str
    members: tuple[ExactDuplicateMember, ...]


def _selected_types(media_filter: str) -> tuple[str, ...]:
    if media_filter == "photos":
        return ("PHOTO",)
    if media_filter == "videos":
        return ("VIDEO",)
    if media_filter == "all":
        return ("PHOTO", "VIDEO", "SIDECAR", "UNKNOWN")
    raise CatalogError(f"Unsupported duplicate media filter: {media_filter}.")


def _library_id(
    connection: sqlite3.Connection, environment: str, library_name: str
) -> str:
    row = connection.execute(
        """
        SELECT library_id
        FROM library
        WHERE environment = ? AND name = ? COLLATE NOCASE
        """,
        (environment.upper(), library_name.strip()),
    ).fetchone()
    if row is None:
        raise CatalogError(
            f"Library '{library_name}' does not exist in the selected profile."
        )
    return str(row["library_id"])


def list_size_candidates(
    database: Path,
    environment: str,
    library_name: str,
    media_filter: str,
) -> list[SizeCandidateGroup]:
    """List present same-size groups without classifying files as duplicates."""
    require_database(database, environment)
    media_types = _selected_types(media_filter)
    placeholders = ", ".join("?" for _ in media_types)
    with open_database(database) as connection:
        library_id = _library_id(connection, environment, library_name)
        rows = connection.execute(
            f"""
            WITH candidate_sizes AS (
                SELECT fl.size_bytes
                FROM file_location AS fl
                JOIN media_file AS mf ON mf.media_id = fl.media_id
                JOIN source AS s ON s.source_id = fl.source_id
                WHERE s.library_id = ?
                  AND fl.present = 1
                  AND mf.status = 'PRESENT'
                  AND mf.media_type IN ({placeholders})
                GROUP BY fl.size_bytes
                HAVING COUNT(*) > 1
            )
            SELECT
                mf.media_id,
                s.name AS source_name,
                fl.relative_path,
                fl.normalized_relative_path,
                mf.media_type,
                fl.size_bytes,
                attempt.digest AS sha256
            FROM file_location AS fl
            JOIN media_file AS mf ON mf.media_id = fl.media_id
            JOIN source AS s ON s.source_id = fl.source_id
            JOIN candidate_sizes AS candidate ON candidate.size_bytes = fl.size_bytes
            LEFT JOIN media_hash AS current ON current.media_id = mf.media_id
            LEFT JOIN hash_attempt AS attempt ON attempt.hash_id = current.hash_id
            WHERE s.library_id = ?
              AND fl.present = 1
              AND mf.status = 'PRESENT'
              AND mf.media_type IN ({placeholders})
            ORDER BY
                fl.size_bytes DESC,
                s.name COLLATE NOCASE,
                fl.normalized_relative_path,
                fl.relative_path,
                mf.media_id
            """,
            (library_id, *media_types, library_id, *media_types),
        ).fetchall()

    groups: list[SizeCandidateGroup] = []
    members: list[SizeCandidateMember] = []
    active_size: int | None = None
    for row in rows:
        size_bytes = int(row["size_bytes"])
        if active_size is not None and size_bytes != active_size:
            groups.append(SizeCandidateGroup(active_size, tuple(members)))
            members = []
        active_size = size_bytes
        members.append(
            SizeCandidateMember(
                media_id=row["media_id"],
                source_name=row["source_name"],
                relative_path=row["relative_path"],
                media_type=row["media_type"],
                size_bytes=size_bytes,
                sha256=row["sha256"],
            )
        )
    if active_size is not None:
        groups.append(SizeCandidateGroup(active_size, tuple(members)))
    return groups


def list_exact_duplicates(
    database: Path,
    environment: str,
    library_name: str,
    media_filter: str,
) -> list[ExactDuplicateGroup]:
    """List present exact-content groups without selecting or changing any copy."""
    require_database(database, environment)
    media_types = _selected_types(media_filter)
    placeholders = ", ".join("?" for _ in media_types)
    with open_database(database) as connection:
        library_id = _library_id(connection, environment, library_name)
        rows = connection.execute(
            f"""
            WITH exact_digests AS (
                SELECT attempt.digest
                FROM media_hash AS current
                JOIN hash_attempt AS attempt ON attempt.hash_id = current.hash_id
                JOIN media_file AS mf ON mf.media_id = current.media_id
                JOIN file_location AS fl ON fl.media_id = mf.media_id
                JOIN source AS s ON s.source_id = fl.source_id
                WHERE s.library_id = ?
                  AND fl.present = 1
                  AND mf.status = 'PRESENT'
                  AND mf.media_type IN ({placeholders})
                  AND attempt.algorithm = 'SHA256'
                  AND attempt.status = 'SUCCESS'
                GROUP BY attempt.digest
                HAVING COUNT(*) > 1
            )
            SELECT
                attempt.digest AS sha256,
                mf.media_id,
                s.name AS source_name,
                fl.relative_path,
                fl.normalized_relative_path,
                mf.media_type,
                fl.size_bytes
            FROM media_hash AS current
            JOIN hash_attempt AS attempt ON attempt.hash_id = current.hash_id
            JOIN media_file AS mf ON mf.media_id = current.media_id
            JOIN file_location AS fl ON fl.media_id = mf.media_id
            JOIN source AS s ON s.source_id = fl.source_id
            JOIN exact_digests AS exact ON exact.digest = attempt.digest
            WHERE s.library_id = ?
              AND fl.present = 1
              AND mf.status = 'PRESENT'
              AND mf.media_type IN ({placeholders})
            ORDER BY
                attempt.digest,
                s.name COLLATE NOCASE,
                fl.normalized_relative_path,
                fl.relative_path,
                mf.media_id
            """,
            (library_id, *media_types, library_id, *media_types),
        ).fetchall()

    groups: list[ExactDuplicateGroup] = []
    members: list[ExactDuplicateMember] = []
    active_digest: str | None = None
    for row in rows:
        digest = str(row["sha256"])
        if active_digest is not None and digest != active_digest:
            groups.append(ExactDuplicateGroup(active_digest, tuple(members)))
            members = []
        active_digest = digest
        members.append(
            ExactDuplicateMember(
                media_id=row["media_id"],
                source_name=row["source_name"],
                relative_path=row["relative_path"],
                media_type=row["media_type"],
                size_bytes=int(row["size_bytes"]),
            )
        )
    if active_digest is not None:
        groups.append(ExactDuplicateGroup(active_digest, tuple(members)))
    return groups
