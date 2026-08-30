"""Datasette metadata generation from versioned catalog inspection queries."""

from __future__ import annotations

import json
from pathlib import Path


def build_datasette_metadata(cache: Path, database: Path) -> Path:
    """Write non-sensitive Datasette query metadata to external cache state."""
    query_directory = Path(__file__).resolve().parents[2] / "queries"
    queries = {
        query_file.stem: {"sql": query_file.read_text(encoding="utf-8")}
        for query_file in sorted(query_directory.glob("*.sql"))
    }
    metadata = {"databases": {database.stem: {"queries": queries}}}
    destination = cache.expanduser().resolve() / "database-browser" / "metadata.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return destination


def build_datasette_command(
    python: str,
    database: Path,
    metadata: Path,
    port: int,
) -> list[str]:
    """Build a loopback command that notices safe external catalog updates."""
    return [
        python,
        "-m",
        "datasette",
        "serve",
        str(database),
        "--metadata",
        str(metadata),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]
