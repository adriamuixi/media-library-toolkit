"""ExifTool adapter for photo metadata extraction."""

from __future__ import annotations

from pathlib import Path
import json
import subprocess
from typing import Any

from media_toolkit.errors import ExternalToolError
from media_toolkit.metadata.geometry import derive_geometry
from media_toolkit.metadata.models import AdapterExtraction, NormalizedMetadata, ToolStatus
from media_toolkit.metadata.tools import inspect_tool


def _leaf_mapping(raw: dict[str, Any]) -> dict[str, Any]:
    return {key.rsplit(":", 1)[-1].casefold(): value for key, value in raw.items()}


def _integer(value: Any) -> int | None:
    try:
        return int(float(value)) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _rotation(orientation: Any) -> int | None:
    numeric = _integer(orientation)
    return {6: 90, 8: 270, 3: 180}.get(numeric, 0 if numeric == 1 else None)


class ExifToolAdapter:
    """Extract photo metadata through ExifTool without invoking a shell."""

    extractor_name = "EXIFTOOL"

    def __init__(self, command: str, timeout_seconds: int, panorama_threshold: float):
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.panorama_threshold = panorama_threshold

    def status(self) -> ToolStatus:
        """Inspect ExifTool availability and version."""
        return inspect_tool("ExifTool", self.command, ["-ver"])

    def extract(self, path: Path, status: ToolStatus) -> AdapterExtraction:
        """Extract a complete grouped JSON record and normalize V1 fields."""
        if not status.available:
            raise ExternalToolError(status.error or "ExifTool is unavailable.")
        try:
            completed = subprocess.run(
                [status.command, "-json", "-n", "-G1", str(path)],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExternalToolError(f"ExifTool execution failed: {exc}") from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or f"Exited with code {completed.returncode}."
            raise ExternalToolError(f"ExifTool failed: {message}")
        try:
            records = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ExternalToolError("ExifTool returned invalid JSON.") from exc
        if not isinstance(records, list) or len(records) != 1 or not isinstance(records[0], dict):
            raise ExternalToolError("ExifTool did not return exactly one metadata record.")

        raw = records[0]
        values = _leaf_mapping(raw)
        width = _integer(values.get("imagewidth") or values.get("exifimagewidth"))
        height = _integer(values.get("imageheight") or values.get("exifimageheight"))
        rotation = _rotation(values.get("orientation"))
        projection = values.get("projectiontype") or values.get("usepanoramaviewer")
        projection_text = str(projection) if projection is not None else None
        geometry = derive_geometry(
            width, height, rotation, projection_text, self.panorama_threshold
        )
        normalized = NormalizedMetadata(
            stored_width_px=width,
            stored_height_px=height,
            display_width_px=geometry.display_width_px,
            display_height_px=geometry.display_height_px,
            megapixels=geometry.megapixels,
            aspect_ratio=geometry.aspect_ratio,
            orientation_class=geometry.orientation_class,
            is_panorama=geometry.is_panorama,
            panorama_reason=geometry.panorama_reason,
            projection_type=projection_text,
            rotation_degrees=rotation,
            camera_make=_text(values.get("make")),
            camera_model=_text(values.get("model")),
            lens_model=_text(values.get("lensmodel") or values.get("lens")),
            iso=_integer(values.get("iso")),
            aperture=_number(values.get("aperture") or values.get("fnumber")),
            exposure_time_seconds=_number(values.get("exposuretime")),
            color_space=_text(values.get("colorspace") or values.get("profiledescription")),
        )
        return AdapterExtraction(raw_metadata=raw, normalized=normalized)


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
