"""Safety validation for read-only media scans."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from media_toolkit.errors import MediaToolkitError


def resolve_media_root(root: Path) -> Path:
    """Resolve and validate an existing media directory."""
    try:
        resolved = root.expanduser().resolve(strict=True)
    except OSError as exc:
        raise MediaToolkitError(f"Media root does not exist or cannot be resolved: {root}") from exc
    if not resolved.is_dir():
        raise MediaToolkitError(f"Media root is not a directory: {resolved}")
    return resolved


def ensure_external_working_paths(root: Path, paths: Iterable[Path]) -> None:
    """Reject generated-state paths located inside the media root."""
    resolved_root = resolve_media_root(root)
    for path in paths:
        resolved_path = path.expanduser().resolve()
        if resolved_path == resolved_root or resolved_path.is_relative_to(resolved_root):
            raise MediaToolkitError(
                "Generated application state must remain outside the media root: "
                f"{resolved_path}"
            )
