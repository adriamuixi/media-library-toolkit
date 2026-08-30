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
    resume_scan_id: str | None = None


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
    resumed: bool


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _normalize_relative_path(relative_path: str) -> str:
    return unicodedata.normalize("NFC", relative_path).casefold()


def _scan_arguments(request: ScanRequest) -> str:
    return json.dumps(
        {
            "include_hidden": request.include_hidden,
            "media_filter": request.media_filter,
        },
        sort_keys=True,
    )


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
    arguments = _scan_arguments(request)
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
    LOGGER.info("Created resumable scan scan_id=%s", scan_id)
    return scan_id


def _resume_scan(
    connection: sqlite3.Connection,
    request: ScanRequest,
    library_id: str,
    source_id: str,
    root: Path,
) -> sqlite3.Row:
    requested_scan_id = request.resume_scan_id
    if requested_scan_id is None:
        raise ValueError("A resume scan identifier is required.")
    arguments = _scan_arguments(request)
    if requested_scan_id == "latest":
        row = connection.execute(
            """
            SELECT *
            FROM scan
            WHERE
                library_id = ?
                AND source_id = ?
                AND root_path_snapshot = ?
                AND arguments_json = ?
                AND status IN ('RUNNING', 'FAILED')
            ORDER BY started_at DESC, scan_id DESC
            LIMIT 1
            """,
            (library_id, source_id, str(root), arguments),
        ).fetchone()
        if row is None:
            raise CatalogError("No matching resumable scan was found.")
    else:
        row = connection.execute(
            "SELECT * FROM scan WHERE scan_id = ?",
            (requested_scan_id,),
        ).fetchone()
        if row is None:
            raise CatalogError(f"Scan '{requested_scan_id}' does not exist.")

    if row["status"] not in {"RUNNING", "FAILED"}:
        raise CatalogError(
            f"Scan '{row['scan_id']}' has terminal status {row['status']} and cannot be resumed."
        )
    if row["library_id"] != library_id or row["source_id"] != source_id:
        raise CatalogError("Resume library or source does not match the original scan.")
    if row["root_path_snapshot"] != str(root):
        raise CatalogError("Resume root does not match the original scan root.")
    if row["arguments_json"] != arguments:
        raise CatalogError("Resume options do not match the original scan options.")

    checkpoint_count = connection.execute(
        "SELECT COUNT(*) AS count FROM scan_checkpoint WHERE scan_id = ?",
        (row["scan_id"],),
    ).fetchone()["count"]
    processed_count = (
        int(row["discovered_count"])
        + int(row["skipped_count"])
        + int(row["warning_count"])
        + int(row["error_count"])
    )
    if processed_count and not checkpoint_count:
        raise CatalogError(
            "This interrupted scan predates checkpoint support and cannot be resumed safely."
        )

    connection.execute(
        "UPDATE scan SET status = 'RUNNING', finished_at = NULL WHERE scan_id = ?",
        (row["scan_id"],),
    )
    connection.execute(
        "UPDATE scan_checkpoint SET resume_seen = 0 WHERE scan_id = ?",
        (row["scan_id"],),
    )
    connection.commit()
    LOGGER.info("Resuming scan scan_id=%s", row["scan_id"])
    return row


def _checkpoint_key(relative_path: str | None) -> str:
    return relative_path or ""


def _load_checkpoint(
    connection: sqlite3.Connection,
    scan_id: str,
    relative_path: str | None,
) -> sqlite3.Row | None:
    return connection.execute(
        """
        SELECT entry_kind, outcome, size_bytes, modified_time_ns
        FROM scan_checkpoint
        WHERE scan_id = ? AND relative_path = ?
        """,
        (scan_id, _checkpoint_key(relative_path)),
    ).fetchone()


def _record_checkpoint(
    connection: sqlite3.Connection,
    scan_id: str,
    relative_path: str | None,
    entry_kind: str,
    outcome: str,
    size_bytes: int | None = None,
    modified_time_ns: int | None = None,
) -> None:
    connection.execute(
        """
        INSERT INTO scan_checkpoint (
            scan_id,
            relative_path,
            entry_kind,
            outcome,
            size_bytes,
            modified_time_ns,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_id,
            _checkpoint_key(relative_path),
            entry_kind,
            outcome,
            size_bytes,
            modified_time_ns,
            _now(),
        ),
    )


def _is_completed_checkpoint(
    connection: sqlite3.Connection,
    scan_id: str,
    result: DiscoveredFile | SkippedEntry | TraversalIssue,
    expected_outcome: str,
) -> bool:
    relative_path = result.relative_path
    checkpoint = _load_checkpoint(connection, scan_id, relative_path)
    if checkpoint is None:
        return False

    if isinstance(result, DiscoveredFile):
        matches = (
            checkpoint["entry_kind"] == "FILE"
            and checkpoint["size_bytes"] == result.size_bytes
            and checkpoint["modified_time_ns"] == result.modified_time_ns
        )
        compatible_outcome = (
            checkpoint["outcome"] == expected_outcome
            if expected_outcome == "FILTERED"
            else checkpoint["outcome"] in {"NEW", "UPDATED"}
        )
        matches = matches and compatible_outcome
    elif isinstance(result, SkippedEntry):
        matches = (
            checkpoint["entry_kind"] == "SKIPPED"
            and checkpoint["outcome"] == expected_outcome
        )
    else:
        matches = (
            checkpoint["entry_kind"] == "ISSUE"
            and checkpoint["outcome"] == expected_outcome
        )

    if not matches:
        raise CatalogError(
            "A previously checkpointed source entry changed during the interrupted scan: "
            f"{relative_path or '<root>'}. Start a new scan instead."
        )
    connection.execute(
        """
        UPDATE scan_checkpoint
        SET resume_seen = 1
        WHERE scan_id = ? AND relative_path = ?
        """,
        (scan_id, _checkpoint_key(relative_path)),
    )
    return True


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
    resumed = request.resume_scan_id is not None

    try:
        with open_database(request.database) as connection:
            library_id, source_id = _resolve_library_and_source(
                connection,
                request.library_name,
                request.source_name,
                request.environment,
            )
            if resumed:
                resume_row = _resume_scan(
                    connection,
                    request,
                    library_id,
                    source_id,
                    root,
                )
                active_scan_id = resume_row["scan_id"]
                discovered_count = int(resume_row["discovered_count"])
                updated_count = int(resume_row["updated_count"])
                new_count = discovered_count - updated_count
                skipped_count = int(resume_row["skipped_count"])
                warning_count = int(resume_row["warning_count"])
                error_count = int(resume_row["error_count"])
            else:
                active_scan_id = _create_scan(
                    connection, request, library_id, source_id, root
                )
            scan_id = active_scan_id

            processed_since_commit = 0
            for result in walk_regular_files(root, request.include_hidden):
                if isinstance(result, SkippedEntry):
                    if _is_completed_checkpoint(
                        connection,
                        active_scan_id,
                        result,
                        result.reason,
                    ):
                        continue
                    skipped_count += 1
                    _record_checkpoint(
                        connection,
                        active_scan_id,
                        result.relative_path,
                        "SKIPPED",
                        result.reason,
                    )
                elif isinstance(result, TraversalIssue):
                    if _is_completed_checkpoint(
                        connection,
                        active_scan_id,
                        result,
                        result.error_type,
                    ):
                        continue
                    _record_issue(connection, active_scan_id, result)
                    _record_checkpoint(
                        connection,
                        active_scan_id,
                        result.relative_path,
                        "ISSUE",
                        result.error_type,
                    )
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
                        if _is_completed_checkpoint(
                            connection,
                            active_scan_id,
                            result,
                            "FILTERED",
                        ):
                            continue
                        skipped_count += 1
                        _record_checkpoint(
                            connection,
                            active_scan_id,
                            result.relative_path,
                            "FILE",
                            "FILTERED",
                            result.size_bytes,
                            result.modified_time_ns,
                        )
                    else:
                        if _is_completed_checkpoint(
                            connection,
                            active_scan_id,
                            result,
                            "INVENTORIED",
                        ):
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
                            outcome = "NEW"
                        else:
                            updated_count += 1
                            outcome = "UPDATED"
                        _record_checkpoint(
                            connection,
                            active_scan_id,
                            result.relative_path,
                            "FILE",
                            outcome,
                            result.size_bytes,
                            result.modified_time_ns,
                        )

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

            if resumed:
                unseen_checkpoint_count = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM scan_checkpoint
                    WHERE scan_id = ? AND resume_seen = 0
                    """,
                    (active_scan_id,),
                ).fetchone()["count"]
                if unseen_checkpoint_count:
                    raise CatalogError(
                        "One or more previously checkpointed entries disappeared during the "
                        "interrupted scan. Start a new scan instead."
                    )

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
            connection.execute(
                "DELETE FROM scan_checkpoint WHERE scan_id = ?",
                (active_scan_id,),
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
        resumed=resumed,
    )
