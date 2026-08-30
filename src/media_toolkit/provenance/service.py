"""Open-format exports for critical historical provenance."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


def export_provenance(
    database: Path, environment: str, library_name: str, output: Path, report_format: str
) -> int:
    """Write one exclusive external CSV or JSON provenance export."""
    require_database(database, environment)
    destination = output.expanduser().resolve()
    if destination.exists():
        raise CatalogError(f"Provenance export already exists: {destination}")
    with open_database(database) as connection:
        library = connection.execute(
            "SELECT library_id FROM library WHERE environment = ? AND name = ? COLLATE NOCASE",
            (environment.upper(), library_name.strip()),
        ).fetchone()
        if library is None:
            raise CatalogError(f"Library '{library_name}' does not exist in the selected profile.")
        roots = connection.execute(
            "SELECT DISTINCT root_path_snapshot FROM scan WHERE library_id = ?",
            (library["library_id"],),
        ).fetchall()
        for root_row in roots:
            root = Path(root_row["root_path_snapshot"]).expanduser().resolve()
            if destination == root or destination.is_relative_to(root):
                raise CatalogError("Provenance exports must remain outside media roots.")
        rows = connection.execute(
            """
            SELECT mi.media_item_id, o.media_id, o.original_filename,
                   o.original_relative_path, o.current_relative_path,
                   s.source_type, s.name AS source_name, b.name AS import_batch,
                   mi.sha256, o.source_context_raw, o.source_context_normalized,
                   o.source_context_confidence
            FROM file_observation AS o
            JOIN source AS s ON s.source_id = o.source_id
            JOIN import_batch AS b ON b.import_batch_id = o.import_batch_id
            LEFT JOIN media_item AS mi ON mi.media_item_id = o.media_item_id
            WHERE s.library_id = ?
            ORDER BY o.original_relative_path, o.observation_id
            """,
            (library["library_id"],),
        ).fetchall()
    values = [dict(row) for row in rows]
    destination.parent.mkdir(parents=True, exist_ok=True)
    if report_format == "csv":
        fields = tuple(values[0]) if values else (
            "media_item_id", "media_id", "original_filename", "original_relative_path",
            "current_relative_path", "source_type", "source_name", "import_batch", "sha256",
        )
        with destination.open("x", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(values)
    elif report_format == "json":
        with destination.open("x", encoding="utf-8") as handle:
            json.dump(values, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
    else:
        raise CatalogError(f"Unsupported provenance export format: {report_format}.")
    return len(values)
