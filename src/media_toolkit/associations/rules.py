"""Deterministic Live Photo, RAW/JPEG, and sidecar association rules."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from media_toolkit.associations.models import ObservedMedia, RelationCandidate


RAW_EXTENSIONS = frozenset({".arw", ".cr2", ".cr3", ".dng", ".nef", ".orf", ".raf", ".raw", ".rw2"})
JPEG_EXTENSIONS = frozenset({".jpeg", ".jpg"})
LIVE_PHOTO_EXTENSIONS = frozenset({".heic", ".heif", ".jpeg", ".jpg"})
LIVE_VIDEO_EXTENSIONS = frozenset({".mov"})
RAW_SIDECAR_EXTENSIONS = frozenset({".dop", ".pp3", ".xmp"})


def _candidate(
    primary: ObservedMedia,
    companion: ObservedMedia,
    relation_type: str,
    confidence: str,
    status: str,
    match_method: str,
    relation_key: str,
    primary_role: str,
    companion_role: str,
) -> RelationCandidate:
    return RelationCandidate(
        primary.media_id,
        companion.media_id,
        relation_type,
        confidence,
        status,
        match_method,
        relation_key,
        primary_role,
        companion_role,
    )


def _live_photo_candidates(files: tuple[ObservedMedia, ...]) -> list[RelationCandidate]:
    candidates: dict[tuple[str, str, str], RelationCandidate] = {}
    photos = [item for item in files if item.media_type == "PHOTO"]
    videos = [item for item in files if item.media_type == "VIDEO"]
    photos_by_identifier: dict[str, list[ObservedMedia]] = defaultdict(list)
    videos_by_identifier: dict[str, list[ObservedMedia]] = defaultdict(list)
    for photo in photos:
        for identifier in photo.metadata_identifiers:
            photos_by_identifier[identifier].append(photo)
    for video in videos:
        for identifier in video.metadata_identifiers:
            videos_by_identifier[identifier].append(video)
    for identifier in sorted(set(photos_by_identifier) & set(videos_by_identifier)):
        matched_photos = photos_by_identifier[identifier]
        matched_videos = videos_by_identifier[identifier]
        status = "DETECTED" if len(matched_photos) == len(matched_videos) == 1 else "CONFLICT"
        for photo in matched_photos:
            for video in matched_videos:
                relation = _candidate(
                    photo, video, "LIVE_PHOTO_PAIR", "HIGH", status,
                    "METADATA_IDENTIFIER", identifier, "PHOTO", "VIDEO",
                )
                candidates[(relation.relation_type, photo.media_id, video.media_id)] = relation

    groups: dict[tuple[str, str], list[ObservedMedia]] = defaultdict(list)
    for item in files:
        groups[(item.parent_key, item.stem_key)].append(item)
    for (parent_key, stem_key), members in sorted(groups.items()):
        matched_photos = [
            item for item in members
            if item.media_type == "PHOTO" and item.extension in LIVE_PHOTO_EXTENSIONS
        ]
        matched_videos = [
            item for item in members
            if item.media_type == "VIDEO" and item.extension in LIVE_VIDEO_EXTENSIONS
        ]
        if not matched_photos or not matched_videos:
            continue
        status = "DETECTED" if len(matched_photos) == len(matched_videos) == 1 else "CONFLICT"
        for photo in matched_photos:
            for video in matched_videos:
                key = ("LIVE_PHOTO_PAIR", photo.media_id, video.media_id)
                if key in candidates:
                    continue
                confidence = "MEDIUM" if photo.extension in {".heic", ".heif"} else "LOW"
                candidates[key] = _candidate(
                    photo, video, "LIVE_PHOTO_PAIR", confidence, status,
                    "BASENAME", f"{parent_key}/{stem_key}", "PHOTO", "VIDEO",
                )
    return list(candidates.values())


def _raw_jpeg_candidates(files: tuple[ObservedMedia, ...]) -> list[RelationCandidate]:
    groups: dict[tuple[str, str], list[ObservedMedia]] = defaultdict(list)
    for item in files:
        groups[(item.parent_key, item.stem_key)].append(item)
    result: list[RelationCandidate] = []
    for (parent_key, stem_key), members in sorted(groups.items()):
        raw_files = [item for item in members if item.extension in RAW_EXTENSIONS]
        jpeg_files = [item for item in members if item.extension in JPEG_EXTENSIONS]
        if not raw_files or not jpeg_files:
            continue
        status = "DETECTED" if len(raw_files) == len(jpeg_files) == 1 else "CONFLICT"
        for raw_file in raw_files:
            for jpeg_file in jpeg_files:
                result.append(
                    _candidate(
                        raw_file, jpeg_file, "RAW_JPEG_PAIR", "HIGH", status,
                        "BASENAME", f"{parent_key}/{stem_key}", "RAW", "JPEG",
                    )
                )
    return result


def _sidecar_candidates(files: tuple[ObservedMedia, ...]) -> list[RelationCandidate]:
    groups: dict[tuple[str, str], list[ObservedMedia]] = defaultdict(list)
    for item in files:
        groups[(item.parent_key, item.stem_key)].append(item)
    result: list[RelationCandidate] = []
    for (parent_key, stem_key), members in sorted(groups.items()):
        sidecars = [item for item in members if item.media_type == "SIDECAR"]
        for sidecar in sidecars:
            if sidecar.extension in RAW_SIDECAR_EXTENSIONS:
                raw_targets = [item for item in members if item.extension in RAW_EXTENSIONS]
                targets = raw_targets or [item for item in members if item.media_type == "PHOTO"]
            elif sidecar.extension == ".aae":
                targets = [
                    item for item in members
                    if item.media_type == "PHOTO" and item.extension not in RAW_EXTENSIONS
                ]
            elif sidecar.extension == ".thm":
                targets = [item for item in members if item.media_type == "VIDEO"]
            else:
                targets = [item for item in members if item.media_type in {"PHOTO", "VIDEO"}]
            if not targets:
                continue
            status = "DETECTED" if len(targets) == 1 else "CONFLICT"
            for target in targets:
                result.append(
                    _candidate(
                        target, sidecar, "SIDECAR_ASSOCIATION", "HIGH", status,
                        "BASENAME", f"{parent_key}/{stem_key}", "MEDIA", "SIDECAR",
                    )
                )
    return result


def detect_relations(files: Iterable[ObservedMedia]) -> tuple[RelationCandidate, ...]:
    """Return all associations in stable order with conflicts left explicit."""
    materialized = tuple(files)
    relations = [
        *_live_photo_candidates(materialized),
        *_raw_jpeg_candidates(materialized),
        *_sidecar_candidates(materialized),
    ]
    return tuple(
        sorted(
            relations,
            key=lambda item: (
                item.relation_type,
                item.relation_key,
                item.primary_media_id,
                item.companion_media_id,
            ),
        )
    )
