"""Read-only import checks and immutable completion verification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


@dataclass(frozen=True)
class ImportBatchSummary:
    """Completeness evidence for one immutable import batch."""

    import_batch_id: str
    name: str
    observation_count: int
    hashed_count: int
    metadata_count: int
    dated_count: int
    historical_duplicate_observation_count: int
    verified_at: str | None


def _batch(connection: sqlite3.Connection, environment: str, library_name: str, batch_name: str) -> sqlite3.Row:
    row = connection.execute(
        """SELECT b.import_batch_id, b.name FROM import_batch AS b
        JOIN library AS l ON l.library_id = b.library_id
        WHERE l.environment = ? AND l.name = ? COLLATE NOCASE AND b.name = ? COLLATE NOCASE""",
        (environment.upper(), library_name.strip(), batch_name.strip()),
    ).fetchone()
    if row is None:
        raise CatalogError(f"Import batch '{batch_name}' does not exist in library '{library_name}'.")
    return row


def get_import_batch_summary(
    database: Path, environment: str, library_name: str, batch_name: str
) -> ImportBatchSummary:
    """Return cross-history completeness evidence without changing catalog state."""
    require_database(database, environment)
    with open_database(database) as connection:
        batch = _batch(connection, environment, library_name, batch_name)
        batch_id = str(batch["import_batch_id"])
        counts = connection.execute(
            """
            SELECT
              COUNT(DISTINCT o.observation_id) AS observation_count,
              COUNT(DISTINCT CASE WHEN h.hash_id IS NOT NULL THEN o.observation_id END) AS hashed_count,
              COUNT(DISTINCT CASE WHEN mm.media_id IS NOT NULL THEN o.observation_id END) AS metadata_count,
              COUNT(DISTINCT CASE WHEN resolution.media_id IS NOT NULL THEN o.observation_id END) AS dated_count,
              COUNT(DISTINCT CASE WHEN EXISTS (
                  SELECT 1 FROM file_observation AS historical
                  WHERE historical.media_item_id = o.media_item_id
                    AND historical.import_batch_id <> o.import_batch_id
              ) THEN o.observation_id END) AS historical_duplicate_observation_count
            FROM file_observation AS o
            LEFT JOIN media_hash AS h ON h.media_id = o.media_id
            LEFT JOIN media_metadata AS mm ON mm.media_id = o.media_id
            LEFT JOIN media_date_resolution AS resolution ON resolution.media_id = o.media_id
            WHERE o.import_batch_id = ?
            """,
            (batch_id,),
        ).fetchone()
        verification = connection.execute(
            "SELECT verified_at FROM import_batch_verification WHERE import_batch_id = ?", (batch_id,)
        ).fetchone()
    return ImportBatchSummary(
        import_batch_id=batch_id,
        name=str(batch["name"]),
        observation_count=int(counts["observation_count"]),
        hashed_count=int(counts["hashed_count"]),
        metadata_count=int(counts["metadata_count"]),
        dated_count=int(counts["dated_count"]),
        historical_duplicate_observation_count=int(counts["historical_duplicate_observation_count"]),
        verified_at=None if verification is None else str(verification["verified_at"]),
    )


def verify_import_batch(
    database: Path, environment: str, library_name: str, batch_name: str
) -> ImportBatchSummary:
    """Persist one immutable completion record after every required read-only stage exists."""
    summary = get_import_batch_summary(database, environment, library_name, batch_name)
    if summary.observation_count == 0:
        raise CatalogError("Import batch verification requires at least one observed file.")
    missing = []
    for label, count in (("hash", summary.hashed_count), ("metadata", summary.metadata_count), ("date resolution", summary.dated_count)):
        if count != summary.observation_count:
            missing.append(label)
    if missing:
        raise CatalogError("Import batch is incomplete: missing " + ", ".join(missing) + ".")
    if summary.verified_at is not None:
        return summary
    verified_at = datetime.now(UTC).isoformat()
    payload = json.dumps(asdict(summary), sort_keys=True, separators=(",", ":"))
    with open_database(database) as connection:
        connection.execute(
            """INSERT INTO import_batch_verification (
            verification_id, import_batch_id, verified_at, observation_count, hashed_count,
            metadata_count, dated_count, historical_duplicate_observation_count, verification_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid4()), summary.import_batch_id, verified_at, summary.observation_count,
             summary.hashed_count, summary.metadata_count, summary.dated_count,
             summary.historical_duplicate_observation_count, payload),
        )
    return ImportBatchSummary(**{**asdict(summary), "verified_at": verified_at})
