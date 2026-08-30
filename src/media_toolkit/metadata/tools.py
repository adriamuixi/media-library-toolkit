"""Safe external-tool discovery and subprocess execution."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess

from media_toolkit.metadata.models import ToolStatus


def resolve_command(command: str) -> str | None:
    """Resolve an executable name or explicit path without invoking a shell."""
    candidate = Path(command).expanduser()
    if candidate.parent != Path(".") or candidate.is_absolute():
        return str(candidate.resolve()) if candidate.is_file() else None
    return shutil.which(command)


def inspect_tool(name: str, command: str, version_arguments: list[str]) -> ToolStatus:
    """Return tool availability without raising for expected installation failures."""
    executable = resolve_command(command)
    if executable is None:
        return ToolStatus(name, command, False, None, "Executable was not found.")
    try:
        completed = subprocess.run(
            [executable, *version_arguments],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return ToolStatus(name, executable, False, None, str(exc))
    if completed.returncode != 0:
        error = completed.stderr.strip() or f"Exited with code {completed.returncode}."
        return ToolStatus(name, executable, False, None, error)
    first_line = (completed.stdout.strip() or completed.stderr.strip()).splitlines()
    version = first_line[0].strip() if first_line else "UNKNOWN"
    return ToolStatus(name, executable, True, version, None)
