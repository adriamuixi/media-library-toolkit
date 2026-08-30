"""Shared metadata adapter models."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class ToolStatus:
    """Availability and version information for one external tool."""

    name: str
    command: str
    available: bool
    version: str | None
    error: str | None


@dataclass(frozen=True)
class NormalizedMetadata:
    """Queryable V1 metadata shared by photos and videos."""

    stored_width_px: int | None = None
    stored_height_px: int | None = None
    display_width_px: int | None = None
    display_height_px: int | None = None
    megapixels: float | None = None
    aspect_ratio: float | None = None
    orientation_class: str = "UNKNOWN"
    is_panorama: bool = False
    panorama_reason: str = "UNKNOWN_DIMENSIONS"
    projection_type: str | None = None
    duration_ms: int | None = None
    container: str | None = None
    video_codec: str | None = None
    audio_codec: str | None = None
    bitrate_bps: int | None = None
    frame_rate: float | None = None
    is_variable_frame_rate: bool | None = None
    rotation_degrees: int | None = None
    dynamic_range: str | None = None
    audio_sample_rate_hz: int | None = None
    audio_channels: int | None = None
    stream_count: int | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    lens_model: str | None = None
    iso: int | None = None
    aperture: float | None = None
    exposure_time_seconds: float | None = None
    color_space: str | None = None


@dataclass(frozen=True)
class AdapterExtraction:
    """Raw and normalized output produced by one adapter."""

    raw_metadata: dict[str, Any]
    normalized: NormalizedMetadata


class MetadataAdapter(Protocol):
    """Interface implemented by metadata extraction adapters."""

    extractor_name: str

    def status(self) -> ToolStatus:
        """Return availability and version details for the backing tool."""

    def extract(self, path: Path, status: ToolStatus) -> AdapterExtraction:
        """Extract raw and normalized metadata from one media file."""
