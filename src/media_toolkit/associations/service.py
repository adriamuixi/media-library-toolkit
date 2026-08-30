"""SQLite orchestration for deterministic media association detection."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path, PurePosixPath
import sqlite3
from typing import Any
import unicodedata
from uuid import uuid4

from media_toolkit.associations.models import ObservedMedia, RelationCandidate
from media_toolkit.associations.rules import detect_relations
from media_toolkit.catalog.database import open_database, require_database
from media_toolkit.errors import CatalogError


IDENTIFIER_KEYS = frozenset(
    {
        "assetidentifier",
        "com.apple.quicktime.content.identifier",
        "contentidentifier",
        "mediagroupuuid",
    }
)


@dataclass(frozen=True)
class AssociationRequest:
    """Catalog scope for one association detection run."""

    database: Path
    environment: str
    library_name: str
    source_name: str


@dataclass(frozen=True)
class AssociationSummary:
    """Counts produced by association detection."""

    file_count: int
    relation_count: int
    live_photo_count: int
    raw_jpeg_count: int
    sidecar_count: int
    conflict_count: int


@dataclass(frozen=True)
class AssociationRecord:
    """Current relation rendered for review."""

    relation_type: str
    status: str
    confidence: str
    match_method: str
    primary_path: str
    companion_path: str
    active: bool


def _source_row(
    connection: sqlite3.Connection,
    environment: str,
    library_name: str,
    source_name: str,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT l.library_id, s.source_id
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


def _collect_identifiers(value: Any, result: set[str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized_key = key.rsplit(":", 1)[-1].casefold().replace("_", "")
            if normalized_key in IDENTIFIER_KEYS and isinstance(child, (str, int)):
                normalized_value = str(child).strip().casefold()
                if normalized_value:
                    result.add(normalized_value)
            _collect_identifiers(child, result)
    elif isinstance(value, list):
        for child in value:
            _collect_identifiers(child, result)


def _identifiers(raw_json: str | None) -> tuple[str, ...]:
    if raw_json is None:
        return ()
    try:
        raw = json.loads(raw_json)
    except json.JSONDecodeError:
        return ()
    result: set[str] = set()
    _collect_identifiers(raw, result)
    return tuple(sorted(result))


def _observed_files(connection: sqlite3.Connection, source_id: str) -> tuple[ObservedMedia, ...]:
    rows = connection.execute(
        """
        SELECT fl.media_id, fl.relative_path, mf.extension, mf.media_type,
               extraction.raw_metadata_json
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
          AND mf.media_type IN ('PHOTO', 'VIDEO', 'SIDECAR')
        ORDER BY fl.normalized_relative_path, fl.relative_path
        """,
        (source_id,),
    ).fetchall()
    result: list[ObservedMedia] = []
    for row in rows:
        relative = PurePosixPath(row["relative_path"])
        parent_key = unicodedata.normalize("NFC", str(relative.parent)).casefold()
        stem_key = unicodedata.normalize("NFC", relative.stem).casefold()
        result.append(
            ObservedMedia(
                media_id=row["media_id"],
                relative_path=row["relative_path"],
                parent_key=parent_key,
                stem_key=stem_key,
                extension=row["extension"].casefold(),
                media_type=row["media_type"],
                metadata_identifiers=_identifiers(row["raw_metadata_json"]),
            )
        )
    return tuple(result)


def _persist_relation(
    connection: sqlite3.Connection,
    library_id: str,
    source_id: str,
    relation: RelationCandidate,
    timestamp: str,
) -> None:
    details = json.dumps(
        {
            "companion_role": relation.companion_role,
            "primary_role": relation.primary_role,
        },
        sort_keys=True,
    )
    connection.execute(
        """
        INSERT INTO media_relation (
            relation_id, library_id, source_id, primary_media_id,
            companion_media_id, relation_type, confidence, status,
            match_method, relation_key, details_json, active,
            first_detected_at, last_detected_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
        ON CONFLICT(source_id, relation_type, primary_media_id, companion_media_id)
        DO UPDATE SET
            confidence = excluded.confidence,
            status = excluded.status,
            match_method = excluded.match_method,
            relation_key = excluded.relation_key,
            details_json = excluded.details_json,
            active = 1,
            last_detected_at = excluded.last_detected_at
        """,
        (
            str(uuid4()), library_id, source_id,
            relation.primary_media_id, relation.companion_media_id,
            relation.relation_type, relation.confidence, relation.status,
            relation.match_method, relation.relation_key, details,
            timestamp, timestamp,
        ),
    )


def run_association_detection(request: AssociationRequest) -> AssociationSummary:
    """Detect current associations without reading or modifying media files."""
    require_database(request.database, request.environment)
    with open_database(request.database) as connection:
        source = _source_row(
            connection, request.environment, request.library_name, request.source_name
        )
        files = _observed_files(connection, source["source_id"])
        relations = detect_relations(files)
        timestamp = datetime.now(UTC).isoformat()
        connection.execute(
            "UPDATE media_relation SET active = 0 WHERE source_id = ? AND active = 1",
            (source["source_id"],),
        )
        for relation in relations:
            _persist_relation(
                connection, source["library_id"], source["source_id"], relation, timestamp
            )
    return AssociationSummary(
        file_count=len(files),
        relation_count=len(relations),
        live_photo_count=sum(item.relation_type == "LIVE_PHOTO_PAIR" for item in relations),
        raw_jpeg_count=sum(item.relation_type == "RAW_JPEG_PAIR" for item in relations),
        sidecar_count=sum(item.relation_type == "SIDECAR_ASSOCIATION" for item in relations),
        conflict_count=sum(item.status == "CONFLICT" for item in relations),
    )


def list_associations(
    database: Path,
    environment: str,
    library_name: str,
    source_name: str,
    relation_type: str | None = None,
    include_inactive: bool = False,
) -> list[AssociationRecord]:
    """List detected relations with current source-relative paths."""
    require_database(database, environment)
    with open_database(database) as connection:
        source = _source_row(connection, environment, library_name, source_name)
        clauses = ["relation.source_id = ?"]
        parameters: list[object] = [source["source_id"]]
        if relation_type:
            clauses.append("relation.relation_type = ?")
            parameters.append(relation_type)
        if not include_inactive:
            clauses.append("relation.active = 1")
        rows = connection.execute(
            f"""
            SELECT relation.relation_type, relation.status, relation.confidence,
                   relation.match_method, relation.active,
                   primary_location.relative_path AS primary_path,
                   companion_location.relative_path AS companion_path
            FROM media_relation AS relation
            JOIN file_location AS primary_location
              ON primary_location.media_id = relation.primary_media_id
             AND primary_location.source_id = relation.source_id
            JOIN file_location AS companion_location
              ON companion_location.media_id = relation.companion_media_id
             AND companion_location.source_id = relation.source_id
            WHERE {' AND '.join(clauses)}
            ORDER BY relation.relation_type, primary_path, companion_path
            """,
            parameters,
        ).fetchall()
    return [
        AssociationRecord(
            relation_type=row["relation_type"],
            status=row["status"],
            confidence=row["confidence"],
            match_method=row["match_method"],
            primary_path=row["primary_path"],
            companion_path=row["companion_path"],
            active=bool(row["active"]),
        )
        for row in rows
    ]
