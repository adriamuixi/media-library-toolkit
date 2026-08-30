"""Read-only metadata extraction orchestration and catalog persistence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
import logging
from pathlib import Path
import sqlite3
from typing import Mapping
from uuid import uuid4

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError
from media_toolkit.metadata.exiftool import ExifToolAdapter
from media_toolkit.metadata.ffprobe import FfprobeAdapter
from media_toolkit.metadata.models import MetadataAdapter, NormalizedMetadata, ToolStatus
from media_toolkit.scan.safety import (
    ensure_external_working_paths,
    resolve_cataloged_file,
    resolve_media_root,
)


LOGGER = logging.getLogger(__name__)
PARSER_VERSION = 1


@dataclass(frozen=True)
class MetadataRequest:
    """Validated inputs for one read-only metadata extraction run."""

    database: Path
    environment: str
    library_name: str
    source_name: str
    root: Path
    media_filter: str
    batch_size: int
    generated_paths: tuple[Path, ...]
    panorama_threshold: float
    panorama_min_width_px: int
    timeout_seconds: int
    exiftool_command: str
    ffprobe_command: str
    force: bool = False


@dataclass(frozen=True)
class MetadataSummary:
    """Counts produced by a metadata extraction run."""

    selected_count: int
    extracted_count: int
    cached_count: int
    error_count: int


def configured_adapters(request: MetadataRequest) -> dict[str, MetadataAdapter]:
    """Build the standard adapters from validated configuration."""
    return {
        "PHOTO": ExifToolAdapter(
            request.exiftool_command,
            request.timeout_seconds,
            request.panorama_threshold,
            request.panorama_min_width_px,
        ),
        "VIDEO": FfprobeAdapter(
            request.ffprobe_command,
            request.timeout_seconds,
            request.panorama_threshold,
            request.panorama_min_width_px,
        ),
    }


def inspect_configured_tools(request: MetadataRequest) -> tuple[ToolStatus, ToolStatus]:
    """Inspect both configured metadata tools without opening the catalog."""
    adapters = configured_adapters(request)
    return adapters["PHOTO"].status(), adapters["VIDEO"].status()


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _resolve_source(
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


def _selected_types(media_filter: str) -> tuple[str, ...]:
    if media_filter == "photos":
        return ("PHOTO",)
    if media_filter == "videos":
        return ("VIDEO",)
    if media_filter == "all":
        return ("PHOTO", "VIDEO")
    raise CatalogError(f"Unsupported metadata media filter: {media_filter}.")


def _signature(request: MetadataRequest, extractor: str) -> str:
    payload = json.dumps(
        {
            "extractor": extractor,
            "panorama_aspect_ratio_threshold": request.panorama_threshold,
            "panorama_min_width_px": request.panorama_min_width_px,
            "parser_version": PARSER_VERSION,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _record_error(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    adapter: MetadataAdapter,
    status: ToolStatus,
    signature: str,
    error_type: str,
    message: str,
) -> None:
    connection.execute(
        """
        INSERT INTO metadata_extraction (
            extraction_id, media_id, location_id, extractor, extractor_version,
            status, input_size_bytes, input_modified_time_ns, config_signature,
            extracted_at, error_type, error_message
        ) VALUES (?, ?, ?, ?, ?, 'ERROR', ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            row["media_id"],
            row["location_id"],
            adapter.extractor_name,
            status.version,
            row["size_bytes"],
            row["modified_time_ns"],
            signature,
            _now(),
            error_type,
            message,
        ),
    )


def _is_cached(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    adapter: MetadataAdapter,
    status: ToolStatus,
    signature: str,
) -> bool:
    cached = connection.execute(
        """
        SELECT 1
        FROM metadata_extraction
        WHERE media_id = ? AND extractor = ? AND extractor_version IS ?
          AND input_size_bytes = ? AND input_modified_time_ns = ?
          AND config_signature = ? AND status = 'SUCCESS'
        LIMIT 1
        """,
        (
            row["media_id"], adapter.extractor_name, status.version,
            row["size_bytes"], row["modified_time_ns"], signature,
        ),
    ).fetchone()
    return cached is not None


def _record_success(
    connection: sqlite3.Connection,
    row: sqlite3.Row,
    adapter: MetadataAdapter,
    status: ToolStatus,
    signature: str,
    normalized: NormalizedMetadata,
    raw_metadata: dict[str, object],
) -> None:
    extraction_id = str(uuid4())
    timestamp = _now()
    connection.execute(
        """
        INSERT INTO metadata_extraction (
            extraction_id, media_id, location_id, extractor, extractor_version,
            status, input_size_bytes, input_modified_time_ns, config_signature,
            extracted_at, raw_metadata_json
        ) VALUES (?, ?, ?, ?, ?, 'SUCCESS', ?, ?, ?, ?, ?)
        """,
        (
            extraction_id, row["media_id"], row["location_id"],
            adapter.extractor_name, status.version, row["size_bytes"],
            row["modified_time_ns"], signature, timestamp,
            json.dumps(raw_metadata, ensure_ascii=False, sort_keys=True),
        ),
    )
    values = asdict(normalized)
    columns = tuple(values)
    assignments = ", ".join(f"{column} = excluded.{column}" for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    connection.execute(
        f"""
        INSERT INTO media_metadata (
            media_id, extraction_id, {', '.join(columns)}, updated_at
        ) VALUES (?, ?, {placeholders}, ?)
        ON CONFLICT(media_id) DO UPDATE SET
            extraction_id = excluded.extraction_id,
            {assignments},
            updated_at = excluded.updated_at
        """,
        (
            row["media_id"],
            extraction_id,
            *(
                int(value) if isinstance(value, bool) else value
                for value in values.values()
            ),
            timestamp,
        ),
    )


def run_metadata(
    request: MetadataRequest,
    adapters: Mapping[str, MetadataAdapter] | None = None,
) -> MetadataSummary:
    """Extract metadata without modifying media and persist resumable results."""
    require_database(request.database, request.environment)
    root = resolve_media_root(request.root)
    ensure_external_working_paths(root, request.generated_paths)
    active_adapters = dict(adapters or configured_adapters(request))
    statuses = {media_type: adapter.status() for media_type, adapter in active_adapters.items()}
    selected = extracted = cached = errors = pending = 0

    with open_database(request.database) as connection:
        source_id = _resolve_source(
            connection, request.environment, request.library_name, request.source_name
        )
        media_types = _selected_types(request.media_filter)
        placeholders = ", ".join("?" for _ in media_types)
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
            (source_id, *media_types),
        ).fetchall()

        for row in rows:
            selected += 1
            adapter = active_adapters[row["media_type"]]
            status = statuses[row["media_type"]]
            signature = _signature(request, adapter.extractor_name)
            if not request.force and _is_cached(connection, row, adapter, status, signature):
                cached += 1
                continue
            if not status.available:
                _record_error(
                    connection, row, adapter, status, signature,
                    "TOOL_UNAVAILABLE", status.error or "Metadata tool is unavailable.",
                )
                errors += 1
                pending += 1
            else:
                try:
                    path = resolve_cataloged_file(root, row["relative_path"])
                    file_status = path.stat()
                    if (
                        file_status.st_size != row["size_bytes"]
                        or file_status.st_mtime_ns != row["modified_time_ns"]
                    ):
                        raise CatalogError(
                            "File size or modification time changed after inventory; run scan again."
                        )
                    result = adapter.extract(path, status)
                    post_status = path.stat()
                    if (
                        post_status.st_size != file_status.st_size
                        or post_status.st_mtime_ns != file_status.st_mtime_ns
                    ):
                        raise CatalogError(
                            "File size or modification time changed during metadata extraction."
                        )
                    _record_success(
                        connection, row, adapter, status, signature,
                        result.normalized, result.raw_metadata,
                    )
                    extracted += 1
                except Exception as exc:
                    _record_error(
                        connection, row, adapter, status, signature,
                        type(exc).__name__.upper(), str(exc),
                    )
                    LOGGER.warning("Metadata failed path=%s error=%s", row["relative_path"], exc)
                    errors += 1
                pending += 1
            if pending >= request.batch_size:
                connection.commit()
                pending = 0
        connection.commit()

    return MetadataSummary(selected, extracted, cached, errors)
