"""Mandatory immutable-provenance checks for future WRITE plans."""

from __future__ import annotations

from pathlib import Path

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


def require_write_provenance(
    database: Path, environment: str, media_ids: tuple[str, ...]
) -> None:
    """Refuse a future WRITE plan unless every media record has durable provenance."""
    require_database(database, environment)
    if not media_ids:
        raise CatalogError("A WRITE provenance check requires at least one media record.")
    placeholders = ", ".join("?" for _ in media_ids)
    with open_database(database) as connection:
        rows = connection.execute(
            f"""
            SELECT mf.media_id,
                   COUNT(o.observation_id) AS observation_count,
                   SUM(CASE WHEN o.original_relative_path <> '' THEN 1 ELSE 0 END)
                       AS original_path_count,
                   SUM(CASE WHEN o.import_batch_id IS NOT NULL THEN 1 ELSE 0 END)
                       AS batch_count,
                   SUM(CASE WHEN o.source_id IS NOT NULL THEN 1 ELSE 0 END)
                       AS source_count,
                   SUM(CASE WHEN o.media_item_id IS NOT NULL THEN 1 ELSE 0 END)
                       AS logical_item_count,
                   SUM(CASE WHEN h.observation_id IS NOT NULL THEN 1 ELSE 0 END)
                       AS location_history_count
            FROM media_file AS mf
            LEFT JOIN file_observation AS o ON o.media_id = mf.media_id
            LEFT JOIN observation_location_history AS h ON h.observation_id = o.observation_id
            WHERE mf.media_id IN ({placeholders})
            GROUP BY mf.media_id
            """,
            media_ids,
        ).fetchall()
    found = {row["media_id"] for row in rows}
    missing = set(media_ids) - found
    if missing:
        raise CatalogError("WRITE provenance check found unknown media records.")
    incomplete = [
        row["media_id"]
        for row in rows
        if not all(
            int(row[column] or 0) > 0
            for column in (
                "observation_count",
                "original_path_count",
                "batch_count",
                "source_count",
                "logical_item_count",
                "location_history_count",
            )
        )
    ]
    if incomplete:
        raise CatalogError(
            "WRITE provenance check failed; every affected media record requires "
            "immutable original path, source, import batch, logical identity, "
            f"and current-location history. Incomplete records: {', '.join(incomplete)}."
        )
