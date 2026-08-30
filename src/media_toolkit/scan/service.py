"""Read-only scan orchestration and SQLite inventory persistence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import sqlite3
import unicodedata
from uuid import uuid4

from media_toolkit import __version__
from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError
from media_toolkit.scan.classification import classify_path, matches_media_filter
from media_toolkit.scan.safety import ensure_external_working_paths, resolve_media_root
from media_toolkit.scan.walker import DiscoveredFile, SkippedEntry, TraversalIssue, walk_regular_files


LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanRequest:
    """Validated inputs for one filesystem inventory run."""

    database: Path
    environment: str
    library_name: str
    source_name: str
    root: Path
    media_filter: str
    include_hidden: bool
    batch_size: int
    generated_paths: tuple[Path, ...]


@dataclass(frozen=True)
class ScanSummary:
    """Final counts and identity for one completed scan."""

    scan_id: str
    status: str
    discovered_count: int
    new_count: int
    updated_count: int
    skipped_count: int
    warning_count: int
    error_count: int


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_relative_path(relative_path: str) -> str:
    return unicodedata.normalize("NFC", relative_path).casefold()


def _resolve_library_and_source(
    connection: sqlite3.Connection,
    library_name: str,
    source_name: str,
    environment: str,
) -> tuple[str, str]:
    library = connection.execute(
        """
        SELECT library_id, name
        FROM library
        WHERE name = ? COLLATE NOCASE AND environment = ?
        """,
        (library_name.strip(), environment.upper()),
    ).fetchone()
    if library is None:
        raise CatalogError(
            f"Library '{library_name}' does not exist in the selected profile."
        )
    source = connection.execute(
        """
        SELECT source_id, name
        FROM source
        WHERE library_id = ? AND name = ? COLLATE NOCASE
        """,
        (library["library_id"], source_name.strip()),
    ).fetchone()
    if source is None:
        raise CatalogError(
            f"Source '{source_name}' does not exist in library '{library['name']}'."
        )
    return library["library_id"], source["source_id"]


def _create_scan(
    connection: sqlite3.Connection,
    request: ScanRequest,
    library_id: str,
    source_id: str,
    root: Path,
) -> str:
    scan_id = str(uuid4())
    arguments = json.dumps(
        {
            "include_hidden": request.include_hidden,
            "media_filter": request.media_filter,
        },
        sort_keys=True,
    )
    connection.execute(
        """
        INSERT INTO scan (
            scan_id,
            library_id,
            source_id,
            root_path_snapshot,
            status,
            software_version,
            arguments_json,
            started_at
        ) VALUES (?, ?, ?, ?, 'RUNNING', ?, ?, ?)
        """,
        (
            scan_id,
            library_id,
            source_id,
            str(root),
            __version__,
            arguments,
            _now(),
        ),
    )
    connection.commit()
    return scan_id


def _record_issue(
    connection: sqlite3.Connection,
    scan_id: str,
    issue: TraversalIssue,
) -> None:
    connection.execute(
        """
        INSERT INTO scan_error (
            error_id,
            scan_id,
            relative_path,
            stage,
            severity,
            error_type,
            message,
            created_at
        ) VALUES (?, ?, ?, 'TRAVERSAL', ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            scan_id,
            issue.relative_path,
            issue.severity,
            issue.error_type,
            issue.message,
            _now(),
        ),
    )


def _upsert_file(
    connection: sqlite3.Connection,
    scan_id: str,
    library_id: str,
    source_id: str,
    discovered: DiscoveredFile,
    media_type: str,
) -> bool:
    existing = connection.execute(
        """
        SELECT location_id, media_id
        FROM file_location
        WHERE source_id = ? AND relative_path = ?
        """,
        (source_id, discovered.relative_path),
    ).fetchone()
    timestamp = _now()
    extension = discovered.path.suffix.casefold()
    if existing is None:
        media_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO media_file (
                media_id,
                library_id,
                original_filename,
                extension,
                media_type,
                size_bytes,
                first_discovered_at,
                last_seen_at,
                status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PRESENT')
            """,
            (
                media_id,
                library_id,
                discovered.path.name,
                extension,
                media_type,
                discovered.size_bytes,
                timestamp,
                timestamp,
            ),
        )
        connection.execute(
            """
            INSERT INTO file_location (
                location_id,
                media_id,
                source_id,
                relative_path,
                normalized_relative_path,
                filename,
                size_bytes,
                modified_time_ns,
                changed_time_ns,
                birth_time_ns,
                first_seen_scan_id,
                last_seen_scan_id,
                present
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                str(uuid4()),
                media_id,
                source_id,
                discovered.relative_path,
                _normalize_relative_path(discovered.relative_path),
                discovered.path.name,
                discovered.size_bytes,
                discovered.modified_time_ns,
                discovered.changed_time_ns,
                discovered.birth_time_ns,
                scan_id,
                scan_id,
            ),
        )
        return True

    connection.execute(
        """
        UPDATE media_file
        SET extension = ?, media_type = ?, size_bytes = ?, last_seen_at = ?, status = 'PRESENT'
        WHERE media_id = ?
        """,
        (
            extension,
            media_type,
            discovered.size_bytes,
            timestamp,
            existing["media_id"],
        ),
    )
    connection.execute(
        """
        UPDATE file_location
        SET
            normalized_relative_path = ?,
            filename = ?,
            size_bytes = ?,
            modified_time_ns = ?,
            changed_time_ns = ?,
            birth_time_ns = ?,
            last_seen_scan_id = ?,
            present = 1
        WHERE location_id = ?
        """,
        (
            _normalize_relative_path(discovered.relative_path),
            discovered.path.name,
            discovered.size_bytes,
            discovered.modified_time_ns,
            discovered.changed_time_ns,
            discovered.birth_time_ns,
            scan_id,
            existing["location_id"],
        ),
    )
    return False


def _update_scan_counts(
    connection: sqlite3.Connection,
    scan_id: str,
    discovered_count: int,
    updated_count: int,
    skipped_count: int,
    warning_count: int,
    error_count: int,
    *,
    status: str = "RUNNING",
    finished_at: str | None = None,
) -> None:
    connection.execute(
        """
        UPDATE scan
        SET
            status = ?,
            finished_at = ?,
            discovered_count = ?,
            updated_count = ?,
            skipped_count = ?,
            warning_count = ?,
            error_count = ?
        WHERE scan_id = ?
        """,
        (
            status,
            finished_at,
            discovered_count,
            updated_count,
            skipped_count,
            warning_count,
            error_count,
            scan_id,
        ),
    )


def run_scan(request: ScanRequest) -> ScanSummary:
    """Inventory one source root without opening or modifying media files."""
    if request.batch_size < 1:
        raise ValueError("Scan batch size must be at least 1.")
    if request.media_filter not in {"photos", "videos", "all"}:
        raise ValueError(f"Unsupported media filter: {request.media_filter}")

    root = resolve_media_root(request.root)
    ensure_external_working_paths(root, request.generated_paths)
    require_database(request.database, request.environment)

    scan_id: str | None = None
    status = "FAILED"
    discovered_count = 0
    new_count = 0
    updated_count = 0
    skipped_count = 0
    warning_count = 0
    error_count = 0

    try:
        with open_database(request.database) as connection:
            library_id, source_id = _resolve_library_and_source(
                connection,
                request.library_name,
                request.source_name,
                request.environment,
            )
            active_scan_id = _create_scan(
                connection, request, library_id, source_id, root
            )
            scan_id = active_scan_id

            processed_since_commit = 0
            for result in walk_regular_files(root, request.include_hidden):
                if isinstance(result, SkippedEntry):
                    skipped_count += 1
                elif isinstance(result, TraversalIssue):
                    _record_issue(connection, active_scan_id, result)
                    if result.severity == "ERROR":
                        error_count += 1
                        LOGGER.error(
                            "scan_id=%s path=%s type=%s message=%s",
                            active_scan_id,
                            result.relative_path,
                            result.error_type,
                            result.message,
                        )
                    else:
                        warning_count += 1
                        LOGGER.warning(
                            "scan_id=%s path=%s type=%s message=%s",
                            active_scan_id,
                            result.relative_path,
                            result.error_type,
                            result.message,
                        )
                else:
                    media_type = classify_path(result.path)
                    if not matches_media_filter(media_type, request.media_filter):
                        skipped_count += 1
                        continue
                    discovered_count += 1
                    created = _upsert_file(
                        connection,
                        active_scan_id,
                        library_id,
                        source_id,
                        result,
                        media_type,
                    )
                    if created:
                        new_count += 1
                    else:
                        updated_count += 1

                processed_since_commit += 1
                if processed_since_commit >= request.batch_size:
                    _update_scan_counts(
                        connection,
                        active_scan_id,
                        discovered_count,
                        updated_count,
                        skipped_count,
                        warning_count,
                        error_count,
                    )
                    connection.commit()
                    processed_since_commit = 0

            status = "COMPLETED_WITH_ERRORS" if error_count else "COMPLETED"
            _update_scan_counts(
                connection,
                active_scan_id,
                discovered_count,
                updated_count,
                skipped_count,
                warning_count,
                error_count,
                status=status,
                finished_at=_now(),
            )
    except Exception:
        if scan_id is not None:
            try:
                with open_database(request.database) as connection:
                    connection.execute(
                        "UPDATE scan SET status = 'FAILED', finished_at = ? WHERE scan_id = ?",
                        (_now(), scan_id),
                    )
            except sqlite3.Error:
                LOGGER.exception("Failed to record terminal scan failure scan_id=%s", scan_id)
        raise

    if scan_id is None:
        raise RuntimeError("Scan completed without a scan identifier.")
    return ScanSummary(
        scan_id=scan_id,
        status=status,
        discovered_count=discovered_count,
        new_count=new_count,
        updated_count=updated_count,
        skipped_count=skipped_count,
        warning_count=warning_count,
        error_count=error_count,
    )
