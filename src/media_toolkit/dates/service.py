"""Catalog-backed capture-date resolution service."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.dates.models import DateCandidate, DateResolution
from media_toolkit.dates.resolver import (
    filename_candidates,
    filesystem_candidates,
    metadata_candidates,
    resolve_date,
)
from media_toolkit.errors import CatalogError


RESOLVER_VERSION = 1


@dataclass(frozen=True)
class DateResolutionRequest:
    """Inputs for deterministic catalog-only date resolution."""

    database: Path
    environment: str
    library_name: str
    source_name: str
    media_filter: str
    batch_size: int
    future_tolerance_days: int
    conflict_tolerance_seconds: int
    suspicious_year_at_or_before: int
    filesystem_gap_days: int
    allow_filesystem_fallback: bool
    force: bool = False


@dataclass(frozen=True)
class DateResolutionSummary:
    """Counts for one date-resolution run."""

    selected_count: int
    resolved_count: int
    suspicious_count: int
    conflict_count: int
    no_date_count: int
    cached_count: int


@dataclass(frozen=True)
class DateResolutionRecord:
    """One queryable current date-resolution row for CLI review."""

    relative_path: str
    media_type: str
    status: str
    effective_capture_local: str | None
    capture_timezone: str | None
    capture_date_source: str | None
    capture_date_precision: str
    capture_date_confidence: str
    reasons: tuple[str, ...]


def _selected_types(media_filter: str) -> tuple[str, ...]:
    if media_filter == "photos":
        return ("PHOTO",)
    if media_filter == "videos":
        return ("VIDEO",)
    if media_filter == "all":
        return ("PHOTO", "VIDEO")
    raise CatalogError(f"Unsupported date media filter: {media_filter}.")


def _source_row(
    connection: sqlite3.Connection,
    environment: str,
    library_name: str,
    source_name: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT s.source_id, s.default_timezone
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
    return row


def _raw_metadata(value: str | None) -> dict[str, object] | None:
    if value is None:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _candidate_json(candidate: DateCandidate) -> dict[str, object | None]:
    values = asdict(candidate)
    values["local_datetime"] = candidate.local_datetime.isoformat()
    values["utc_datetime"] = (
        candidate.utc_datetime.astimezone(UTC).isoformat()
        if candidate.utc_datetime is not None
        else None
    )
    return values


def _input_signature(request: DateResolutionRequest, row: sqlite3.Row) -> str:
    payload = json.dumps(
        {
            "allow_filesystem_fallback": request.allow_filesystem_fallback,
            "birth_time_ns": row["birth_time_ns"],
            "conflict_tolerance_seconds": request.conflict_tolerance_seconds,
            "default_timezone": row["default_timezone"],
            "extraction_id": row["extraction_id"],
            "filename": row["filename"],
            "filesystem_gap_days": request.filesystem_gap_days,
            "future_tolerance_days": request.future_tolerance_days,
            "media_type": row["media_type"],
            "modified_time_ns": row["modified_time_ns"],
            "resolver_version": RESOLVER_VERSION,
            "suspicious_year_at_or_before": request.suspicious_year_at_or_before,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _is_cached(connection: sqlite3.Connection, media_id: str, signature: str) -> bool:
    row = connection.execute(
        """
        SELECT 1
        FROM media_date_resolution AS current
        JOIN date_resolution_attempt AS attempt
          ON attempt.resolution_id = current.resolution_id
        WHERE current.media_id = ? AND attempt.input_signature = ?
        """,
        (media_id, signature),
    ).fetchone()
    return row is not None


def _persist_resolution(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    signature: str,
    resolution: DateResolution,
) -> None:
    selected = resolution.selected
    resolution_id = str(uuid4())
    timestamp = datetime.now(UTC).isoformat()
    connection.execute(
        """
        INSERT INTO date_resolution_attempt (
            resolution_id, media_id, extraction_id, status,
            effective_capture_local, effective_capture_at_utc,
            capture_timezone, timezone_source, capture_date_source,
            capture_date_precision, capture_date_confidence, input_signature,
            candidates_json, reasons_json, resolved_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            resolution_id,
            row["media_id"],
            row["extraction_id"],
            resolution.status,
            selected.local_datetime.isoformat() if selected else None,
            selected.utc_datetime.astimezone(UTC).isoformat()
            if selected and selected.utc_datetime
            else None,
            selected.timezone_name if selected else None,
            selected.timezone_source if selected else "UNKNOWN",
            selected.source if selected else None,
            selected.precision if selected else "UNKNOWN",
            selected.confidence if selected else "UNKNOWN",
            signature,
            json.dumps(
                [_candidate_json(candidate) for candidate in resolution.candidates],
                ensure_ascii=False,
                sort_keys=True,
            ),
            json.dumps(resolution.reasons, sort_keys=True),
            timestamp,
        ),
    )
    connection.execute(
        """
        INSERT INTO media_date_resolution (media_id, resolution_id, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(media_id) DO UPDATE SET
            resolution_id = excluded.resolution_id,
            updated_at = excluded.updated_at
        """,
        (row["media_id"], resolution_id, timestamp),
    )


def run_date_resolution(
    request: DateResolutionRequest,
    *,
    now: datetime | None = None,
) -> DateResolutionSummary:
    """Resolve effective dates using only previously cataloged evidence."""
    require_database(request.database, request.environment)
    types = _selected_types(request.media_filter)
    resolved = suspicious = conflict = no_date = cached = pending = 0
    current_time = now or datetime.now(UTC)
    with open_database(request.database) as connection:
        source = _source_row(
            connection, request.environment, request.library_name, request.source_name
        )
        placeholders = ", ".join("?" for _ in types)
        rows = connection.execute(
            f"""
            SELECT fl.media_id, fl.filename, fl.relative_path,
                   fl.modified_time_ns, fl.birth_time_ns, mf.media_type,
                   ? AS default_timezone,
                   extraction.extraction_id, extraction.raw_metadata_json
            FROM file_location AS fl
            JOIN media_file AS mf ON mf.media_id = fl.media_id
            LEFT JOIN metadata_extraction AS extraction
              ON extraction.extraction_id = (
                  SELECT candidate.extraction_id
                  FROM metadata_extraction AS candidate
                  WHERE candidate.media_id = fl.media_id
                    AND candidate.status = 'SUCCESS'
                  ORDER BY candidate.extracted_at DESC, candidate.extraction_id DESC
                  LIMIT 1
              )
            WHERE fl.source_id = ? AND fl.present = 1 AND mf.status = 'PRESENT'
              AND mf.media_type IN ({placeholders})
            ORDER BY fl.normalized_relative_path, fl.relative_path
            """,
            (source["default_timezone"], source["source_id"], *types),
        ).fetchall()

        for row in rows:
            signature = _input_signature(request, row)
            if not request.force and _is_cached(connection, row["media_id"], signature):
                cached += 1
                continue
            candidates = metadata_candidates(
                _raw_metadata(row["raw_metadata_json"]),
                row["media_type"],
                row["default_timezone"],
            )
            candidates.extend(filename_candidates(row["filename"], row["default_timezone"]))
            candidates.extend(
                filesystem_candidates(
                    row["birth_time_ns"], row["modified_time_ns"],
                    row["default_timezone"], request.allow_filesystem_fallback,
                )
            )
            resolution = resolve_date(
                candidates,
                now=current_time,
                future_tolerance_days=request.future_tolerance_days,
                conflict_tolerance_seconds=request.conflict_tolerance_seconds,
                suspicious_year_at_or_before=request.suspicious_year_at_or_before,
                filesystem_gap_days=request.filesystem_gap_days,
            )
            _persist_resolution(connection, row, signature, resolution)
            if resolution.status == "RESOLVED":
                resolved += 1
            elif resolution.status == "SUSPICIOUS":
                suspicious += 1
            elif resolution.status == "CONFLICT":
                conflict += 1
            else:
                no_date += 1
            pending += 1
            if pending >= request.batch_size:
                connection.commit()
                pending = 0
        connection.commit()
    return DateResolutionSummary(
        len(rows), resolved, suspicious, conflict, no_date, cached
    )


def list_date_resolutions(
    database: Path,
    environment: str,
    library_name: str,
    source_name: str,
    status: str | None = None,
) -> list[DateResolutionRecord]:
    """List current date resolutions in deterministic path order."""
    require_database(database, environment)
    with open_database(database) as connection:
        source = _source_row(connection, environment, library_name, source_name)
        parameters: list[object] = [source["source_id"]]
        status_clause = ""
        if status:
            status_clause = "AND attempt.status = ?"
            parameters.append(status.upper())
        rows = connection.execute(
            f"""
            SELECT fl.relative_path, mf.media_type, attempt.status,
                   attempt.effective_capture_local, attempt.capture_timezone,
                   attempt.capture_date_source, attempt.capture_date_precision,
                   attempt.capture_date_confidence, attempt.reasons_json
            FROM media_date_resolution AS current
            JOIN date_resolution_attempt AS attempt
              ON attempt.resolution_id = current.resolution_id
            JOIN media_file AS mf ON mf.media_id = current.media_id
            JOIN file_location AS fl ON fl.media_id = current.media_id
            WHERE fl.source_id = ? AND fl.present = 1 {status_clause}
            ORDER BY fl.normalized_relative_path, fl.relative_path
            """,
            parameters,
        ).fetchall()
    return [
        DateResolutionRecord(
            relative_path=row["relative_path"],
            media_type=row["media_type"],
            status=row["status"],
            effective_capture_local=row["effective_capture_local"],
            capture_timezone=row["capture_timezone"],
            capture_date_source=row["capture_date_source"],
            capture_date_precision=row["capture_date_precision"],
            capture_date_confidence=row["capture_date_confidence"],
            reasons=tuple(json.loads(row["reasons_json"])),
        )
        for row in rows
    ]
