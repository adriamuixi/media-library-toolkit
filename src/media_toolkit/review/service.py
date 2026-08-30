"""Catalog-only audited decisions for local human review."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


def apply_manual_date_resolution(
    database: Path,
    environment: str,
    media_id: str,
    capture_local: str,
    reason: str,
    decided_by: str,
) -> str:
    """Append an audited manual date decision without modifying media or evidence."""
    require_database(database, environment)
    normalized_reason = reason.strip()
    normalized_decided_by = decided_by.strip()
    if not normalized_reason:
        raise CatalogError("A manual date decision requires a non-empty reason.")
    if not normalized_decided_by:
        raise CatalogError("A manual date decision requires a non-empty reviewer identity.")
    try:
        parsed = datetime.fromisoformat(capture_local)
    except ValueError as exc:
        raise CatalogError("Manual capture date must be an ISO-8601 local datetime.") from exc
    if parsed.tzinfo is not None:
        raise CatalogError("Manual capture date must not include a timezone offset.")
    local_value = parsed.isoformat(timespec="seconds")
    decision_id = str(uuid4())
    resolution_id = str(uuid4())
    timestamp = datetime.now(UTC).isoformat()
    payload = json.dumps(
        {"effective_capture_local": local_value, "resolution_id": resolution_id},
        sort_keys=True,
    )
    with open_database(database) as connection:
        media = connection.execute(
            "SELECT media_id FROM media_file WHERE media_id = ?",
            (media_id,),
        ).fetchone()
        if media is None:
            raise CatalogError(f"Media '{media_id}' does not exist in the selected profile.")
        connection.execute(
            """
            INSERT INTO manual_review_decision (
                decision_id, media_id, decision_type, decision_value_json,
                reason, decided_at, decided_by
            ) VALUES (?, ?, 'DATE_RESOLUTION', ?, ?, ?, ?)
            """,
            (decision_id, media_id, payload, normalized_reason, timestamp, normalized_decided_by),
        )
        connection.execute(
            """
            INSERT INTO date_resolution_attempt (
                resolution_id, media_id, extraction_id, status,
                effective_capture_local, effective_capture_at_utc,
                capture_timezone, timezone_source, capture_date_source,
                capture_date_precision, capture_date_confidence,
                input_signature, candidates_json, reasons_json, resolved_at
            ) VALUES (?, ?, NULL, 'RESOLVED', ?, NULL, NULL, 'UNKNOWN', 'MANUAL',
                      'SECOND', 'HIGH', ?, '[]', ?, ?)
            """,
            (
                resolution_id, media_id, local_value, f"manual:{decision_id}",
                json.dumps(["MANUAL_DECISION"], sort_keys=True), timestamp,
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
            (media_id, resolution_id, timestamp),
        )
    return decision_id
