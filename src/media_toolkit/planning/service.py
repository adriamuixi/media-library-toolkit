"""Deterministic year-or-no-date plan generation without media mutation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from pathlib import Path
from uuid import uuid4

from media_toolkit import __version__
from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


@dataclass(frozen=True)
class PlanSummary:
    """One immutable organization plan summary."""

    plan_id: str
    status: str
    item_count: int
    conflict_count: int
    checksum: str


def create_year_or_no_date_plan(
    database: Path, environment: str, library_name: str
) -> PlanSummary:
    """Create a deterministic DRAFT or REVIEW_REQUIRED catalog plan."""
    require_database(database, environment)
    with open_database(database) as connection:
        library = connection.execute(
            "SELECT library_id FROM library WHERE environment = ? AND name = ? COLLATE NOCASE",
            (environment.upper(), library_name.strip()),
        ).fetchone()
        if library is None:
            raise CatalogError(f"Library '{library_name}' does not exist in the selected profile.")
        rows = connection.execute(
            """
            SELECT o.observation_id, o.media_id, o.original_filename,
                   attempt.status AS date_status, attempt.effective_capture_local
            FROM file_observation AS o
            JOIN source AS s ON s.source_id = o.source_id
            JOIN media_file AS mf ON mf.media_id = o.media_id
            LEFT JOIN media_date_resolution AS current ON current.media_id = o.media_id
            LEFT JOIN date_resolution_attempt AS attempt ON attempt.resolution_id = current.resolution_id
            WHERE s.library_id = ? AND mf.status = 'PRESENT'
            ORDER BY o.original_relative_path, o.observation_id
            """,
            (library["library_id"],),
        ).fetchall()
        proposed = []
        for row in rows:
            year = (
                str(row["effective_capture_local"])[:4]
                if row["date_status"] == "RESOLVED" and row["effective_capture_local"]
                else "no_date"
            )
            proposed.append((row, f"{year}/{row['original_filename']}"))
        destinations = {}
        for row, destination in proposed:
            destinations.setdefault(destination, []).append(row["observation_id"])
        payload = [(row["observation_id"], destination) for row, destination in proposed]
        checksum = sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()
        plan_id = str(uuid4())
        conflicts = sum(len(ids) for ids in destinations.values() if len(ids) > 1)
        status = "REVIEW_REQUIRED" if conflicts else "DRAFT"
        connection.execute(
            """
            INSERT INTO organization_plan (
                plan_id, library_id, status, strategy, checksum, created_at, created_by_version
            ) VALUES (?, ?, ?, 'YEAR_OR_NO_DATE', ?, ?, ?)
            """,
            (plan_id, library["library_id"], status, checksum, datetime.now(UTC).isoformat(), __version__),
        )
        for row, destination in proposed:
            conflict = len(destinations[destination]) > 1
            connection.execute(
                """
                INSERT INTO organization_plan_item (
                    plan_item_id, plan_id, observation_id, media_id,
                    destination_relative_path, status, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()), plan_id, row["observation_id"], row["media_id"], destination,
                    "CONFLICT" if conflict else "PROPOSED",
                    "DESTINATION_COLLISION" if conflict else None,
                ),
            )
    return PlanSummary(plan_id, status, len(proposed), conflicts, checksum)
