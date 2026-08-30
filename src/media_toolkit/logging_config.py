"""Application logging setup."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from pathlib import Path
from uuid import uuid4


def configure_logging(log_directory: Path, level: str, command: str) -> Path:
    """Configure console and per-run file logging outside media roots."""
    log_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_id = uuid4().hex[:8]
    log_path = log_directory / f"{timestamp}_{command}_{run_id}.log"

    formatter = logging.Formatter(
        fmt="%(asctime)sZ %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    formatter.converter = __import__("time").gmtime

    root = logging.getLogger()
    for existing_handler in root.handlers:
        existing_handler.close()
    root.handlers.clear()
    root.setLevel(level)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
    return log_path
