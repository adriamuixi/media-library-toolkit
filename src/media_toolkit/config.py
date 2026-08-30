"""TOML configuration loading and validation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib
from typing import Any, Mapping

from media_toolkit.errors import ConfigurationError


@dataclass(frozen=True)
class ProfileConfig:
    """Database settings for one isolated runtime profile."""

    name: str
    database: Path
    environment: str


@dataclass(frozen=True)
class AppConfig:
    """Validated application configuration."""

    base_directory: Path
    default_profile: str
    log_level: str
    workspace: Path
    logs: Path
    reports: Path
    cache: Path
    profiles: Mapping[str, ProfileConfig]
    default_media_mode: str
    require_write_confirmation: bool
    panorama_aspect_ratio_threshold: float
    metadata_batch_size: int
    metadata_timeout_seconds: int
    exiftool_command: str
    ffprobe_command: str
    date_batch_size: int
    date_future_tolerance_days: int
    date_conflict_tolerance_seconds: int
    date_suspicious_year_at_or_before: int
    date_filesystem_gap_days: int
    date_allow_filesystem_fallback: bool
    hash_batch_size: int
    hash_chunk_size_bytes: int
    duplicate_source_type_priority: tuple[str, ...]
    scan_include_hidden: bool
    scan_batch_size: int

    def profile(self, name: str | None = None) -> ProfileConfig:
        """Return a configured profile or raise a readable error."""
        selected = name or self.default_profile
        try:
            return self.profiles[selected]
        except KeyError as exc:
            choices = ", ".join(sorted(self.profiles))
            raise ConfigurationError(
                f"Unknown profile '{selected}'. Available profiles: {choices}."
            ) from exc


DEFAULTS: dict[str, Any] = {
    "application": {"default_profile": "production", "log_level": "INFO"},
    "paths": {
        "workspace": "./data",
        "logs": "./logs",
        "reports": "./reports",
        "cache": "./cache",
    },
    "profiles": {
        "production": {
            "database": "./data/production/catalog.sqlite3",
            "environment": "PRODUCTION",
        },
        "test": {
            "database": "./data/test/catalog.sqlite3",
            "environment": "TEST",
        },
    },
    "safety": {
        "default_media_mode": "read-only",
        "require_write_confirmation": True,
    },
    "metadata": {
        "panorama_aspect_ratio_threshold": 2.0,
        "batch_size": 100,
        "timeout_seconds": 60,
        "exiftool_command": "exiftool",
        "ffprobe_command": "ffprobe",
    },
    "dates": {
        "batch_size": 500,
        "future_tolerance_days": 2,
        "conflict_tolerance_seconds": 86400,
        "suspicious_year_at_or_before": 1980,
        "filesystem_gap_days": 3650,
        "allow_filesystem_fallback": False,
    },
    "hashing": {"batch_size": 100, "chunk_size_bytes": 8 * 1024 * 1024},
    "duplicates": {"source_type_priority": []},
    "scan": {"include_hidden": False, "batch_size": 500},
}


def _merge(base: dict[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in base.items():
        result[key] = _merge(value, {}) if isinstance(value, dict) else value
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def _absolute(base_directory: Path, value: str) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else (base_directory / path).resolve()


def load_config(
    config_path: Path | None = None,
    *,
    base_directory: Path | None = None,
) -> AppConfig:
    """Load defaults and optionally merge a user TOML file."""
    base = (base_directory or Path.cwd()).resolve()
    override: Mapping[str, Any] = {}
    if config_path is not None:
        resolved = config_path.expanduser().resolve()
        if not resolved.is_file():
            raise ConfigurationError(f"Configuration file does not exist: {resolved}")
        with resolved.open("rb") as handle:
            override = tomllib.load(handle)

    values = _merge(DEFAULTS, override)
    application = values["application"]
    paths = values["paths"]
    safety = values["safety"]
    metadata = values["metadata"]
    dates = values["dates"]
    hashing = values["hashing"]
    duplicates = values["duplicates"]
    scan = values["scan"]

    profiles: dict[str, ProfileConfig] = {}
    for name, raw_profile in values["profiles"].items():
        environment = str(raw_profile["environment"]).upper()
        if environment not in {"TEST", "PRODUCTION"}:
            raise ConfigurationError(
                f"Profile '{name}' has unsupported environment '{environment}'."
            )
        profiles[name] = ProfileConfig(
            name=name,
            database=_absolute(base, str(raw_profile["database"])),
            environment=environment,
        )

    default_profile = str(application["default_profile"])
    if default_profile not in profiles:
        raise ConfigurationError(
            f"Default profile '{default_profile}' is not defined in [profiles]."
        )

    default_media_mode = str(safety["default_media_mode"])
    if default_media_mode != "read-only":
        raise ConfigurationError("The default media mode must be 'read-only'.")

    panorama_threshold = float(metadata["panorama_aspect_ratio_threshold"])
    if panorama_threshold <= 1.0:
        raise ConfigurationError(
            "The panorama aspect-ratio threshold must be greater than 1.0."
        )

    metadata_batch_size = int(metadata["batch_size"])
    if metadata_batch_size < 1:
        raise ConfigurationError("The metadata batch size must be at least 1.")
    metadata_timeout_seconds = int(metadata["timeout_seconds"])
    if metadata_timeout_seconds < 1:
        raise ConfigurationError("The metadata timeout must be at least 1 second.")
    exiftool_command = str(metadata["exiftool_command"]).strip()
    ffprobe_command = str(metadata["ffprobe_command"]).strip()
    if not exiftool_command or not ffprobe_command:
        raise ConfigurationError("Metadata tool commands cannot be empty.")

    date_batch_size = int(dates["batch_size"])
    future_tolerance_days = int(dates["future_tolerance_days"])
    conflict_tolerance_seconds = int(dates["conflict_tolerance_seconds"])
    suspicious_year = int(dates["suspicious_year_at_or_before"])
    filesystem_gap_days = int(dates["filesystem_gap_days"])
    if date_batch_size < 1:
        raise ConfigurationError("The date-resolution batch size must be at least 1.")
    if future_tolerance_days < 0 or conflict_tolerance_seconds < 0:
        raise ConfigurationError("Date tolerances cannot be negative.")
    if suspicious_year < 1 or filesystem_gap_days < 0:
        raise ConfigurationError("Suspicious-date limits are invalid.")

    hash_batch_size = int(hashing["batch_size"])
    hash_chunk_size_bytes = int(hashing["chunk_size_bytes"])
    if hash_batch_size < 1:
        raise ConfigurationError("The hashing batch size must be at least 1.")
    if hash_chunk_size_bytes < 1:
        raise ConfigurationError("The hashing chunk size must be at least 1 byte.")
    raw_priority = duplicates["source_type_priority"]
    if not isinstance(raw_priority, list):
        raise ConfigurationError("Duplicate source type priority must be a TOML array.")
    duplicate_source_type_priority = tuple(
        str(item).strip().upper().replace("-", "_") for item in raw_priority
    )
    if (
        any(not item for item in duplicate_source_type_priority)
        or len(set(duplicate_source_type_priority)) != len(duplicate_source_type_priority)
    ):
        raise ConfigurationError(
            "Duplicate source type priority must contain unique non-empty values."
        )

    scan_batch_size = int(scan["batch_size"])
    if scan_batch_size < 1:
        raise ConfigurationError("The scan batch size must be at least 1.")

    return AppConfig(
        base_directory=base,
        default_profile=default_profile,
        log_level=str(application["log_level"]).upper(),
        workspace=_absolute(base, str(paths["workspace"])),
        logs=_absolute(base, str(paths["logs"])),
        reports=_absolute(base, str(paths["reports"])),
        cache=_absolute(base, str(paths["cache"])),
        profiles=profiles,
        default_media_mode=default_media_mode,
        require_write_confirmation=bool(safety["require_write_confirmation"]),
        panorama_aspect_ratio_threshold=panorama_threshold,
        metadata_batch_size=metadata_batch_size,
        metadata_timeout_seconds=metadata_timeout_seconds,
        exiftool_command=exiftool_command,
        ffprobe_command=ffprobe_command,
        date_batch_size=date_batch_size,
        date_future_tolerance_days=future_tolerance_days,
        date_conflict_tolerance_seconds=conflict_tolerance_seconds,
        date_suspicious_year_at_or_before=suspicious_year,
        date_filesystem_gap_days=filesystem_gap_days,
        date_allow_filesystem_fallback=bool(dates["allow_filesystem_fallback"]),
        hash_batch_size=hash_batch_size,
        hash_chunk_size_bytes=hash_chunk_size_bytes,
        duplicate_source_type_priority=duplicate_source_type_priority,
        scan_include_hidden=bool(scan["include_hidden"]),
        scan_batch_size=scan_batch_size,
    )
