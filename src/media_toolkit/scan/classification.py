"""Deterministic media classification based on file extensions."""

from __future__ import annotations

from pathlib import Path


PHOTO_EXTENSIONS = frozenset(
    {
        ".arw",
        ".avif",
        ".bmp",
        ".cr2",
        ".cr3",
        ".dng",
        ".gif",
        ".heic",
        ".heif",
        ".jpeg",
        ".jpg",
        ".nef",
        ".orf",
        ".png",
        ".raf",
        ".raw",
        ".rw2",
        ".tif",
        ".tiff",
        ".webp",
    }
)

VIDEO_EXTENSIONS = frozenset(
    {
        ".3gp",
        ".avi",
        ".m2ts",
        ".m4v",
        ".mkv",
        ".mov",
        ".mp4",
        ".mpeg",
        ".mpg",
        ".mts",
        ".webm",
    }
)

SIDECAR_EXTENSIONS = frozenset({".aae", ".dop", ".pp3", ".thm", ".xmp"})


def classify_path(path: Path) -> str:
    """Classify one file without reading its contents."""
    extension = path.suffix.casefold()
    if extension in PHOTO_EXTENSIONS:
        return "PHOTO"
    if extension in VIDEO_EXTENSIONS:
        return "VIDEO"
    if extension in SIDECAR_EXTENSIONS:
        return "SIDECAR"
    return "UNKNOWN"


def matches_media_filter(media_type: str, media_filter: str) -> bool:
    """Return whether a classified file belongs to a CLI media filter."""
    if media_filter == "all":
        return True
    if media_filter == "photos":
        return media_type == "PHOTO"
    if media_filter == "videos":
        return media_type == "VIDEO"
    raise ValueError(f"Unsupported media filter: {media_filter}")
