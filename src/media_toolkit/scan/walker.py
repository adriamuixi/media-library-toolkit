"""Streaming, non-following filesystem traversal."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
import os
from pathlib import Path
from typing import TypeAlias


@dataclass(frozen=True)
class DiscoveredFile:
    """A regular file and the filesystem facts collected without opening it."""

    path: Path
    relative_path: str
    size_bytes: int
    modified_time_ns: int
    changed_time_ns: int
    birth_time_ns: int | None


@dataclass(frozen=True)
class TraversalIssue:
    """A non-fatal traversal problem to persist in the scan journal."""

    relative_path: str | None
    severity: str
    error_type: str
    message: str


@dataclass(frozen=True)
class SkippedEntry:
    """An intentionally excluded filesystem entry."""

    relative_path: str
    reason: str


WalkResult: TypeAlias = DiscoveredFile | TraversalIssue | SkippedEntry


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _birth_time_ns(stat_result: os.stat_result) -> int | None:
    explicit = getattr(stat_result, "st_birthtime_ns", None)
    if explicit is not None:
        return int(explicit)
    seconds = getattr(stat_result, "st_birthtime", None)
    return None if seconds is None else int(float(seconds) * 1_000_000_000)


def walk_regular_files(
    root: Path, include_hidden: bool
) -> Generator[WalkResult, None, None]:
    """Yield filesystem results without following symbolic links."""
    directories = [root]
    while directories:
        directory = directories.pop()
        try:
            iterator = os.scandir(directory)
        except OSError as exc:
            relative = None if directory == root else _relative(directory, root)
            yield TraversalIssue(relative, "ERROR", type(exc).__name__, str(exc))
            continue

        with iterator:
            for entry in iterator:
                entry_path = Path(entry.path)
                relative_path = _relative(entry_path, root)
                if not include_hidden and entry.name.startswith("."):
                    yield SkippedEntry(relative_path, "HIDDEN")
                    continue
                try:
                    if entry.is_symlink():
                        yield TraversalIssue(
                            relative_path,
                            "WARNING",
                            "SYMLINK_SKIPPED",
                            "Symbolic links are not followed during scans.",
                        )
                    elif entry.is_dir(follow_symlinks=False):
                        directories.append(entry_path)
                    elif entry.is_file(follow_symlinks=False):
                        stat_result = entry.stat(follow_symlinks=False)
                        yield DiscoveredFile(
                            path=entry_path,
                            relative_path=relative_path,
                            size_bytes=stat_result.st_size,
                            modified_time_ns=stat_result.st_mtime_ns,
                            changed_time_ns=stat_result.st_ctime_ns,
                            birth_time_ns=_birth_time_ns(stat_result),
                        )
                    else:
                        yield TraversalIssue(
                            relative_path,
                            "WARNING",
                            "NON_REGULAR_SKIPPED",
                            "Non-regular filesystem entries are not cataloged.",
                        )
                except OSError as exc:
                    yield TraversalIssue(
                        relative_path,
                        "ERROR",
                        type(exc).__name__,
                        str(exc),
                    )
