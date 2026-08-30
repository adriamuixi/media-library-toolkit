"""Domain models for associated media files."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ObservedMedia:
    """Catalog fields required by deterministic association rules."""

    media_id: str
    relative_path: str
    parent_key: str
    stem_key: str
    extension: str
    media_type: str
    metadata_identifiers: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationCandidate:
    """One detected relation with explicit role and evidence."""

    primary_media_id: str
    companion_media_id: str
    relation_type: str
    confidence: str
    status: str
    match_method: str
    relation_key: str
    primary_role: str
    companion_role: str
