"""ffprobe adapter for video metadata extraction."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import subprocess
from typing import Any

from media_toolkit.errors import ExternalToolError
from media_toolkit.metadata.geometry import derive_geometry
from media_toolkit.metadata.models import AdapterExtraction, NormalizedMetadata, ToolStatus
from media_toolkit.metadata.tools import inspect_tool


def _integer(value: Any) -> int | None:
    try:
        return int(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) if value not in (None, "", "N/A") else None
    except (InvalidOperation, ValueError):
        return None


def _rate(value: Any) -> float | None:
    if not isinstance(value, str) or value in {"0/0", "N/A"}:
        return None
    numerator, separator, denominator = value.partition("/")
    try:
        return float(Decimal(numerator) / Decimal(denominator)) if separator else float(value)
    except (InvalidOperation, ValueError, ZeroDivisionError):
        return None


def _rotation(stream: dict[str, Any]) -> int | None:
    tags = stream.get("tags") if isinstance(stream.get("tags"), dict) else {}
    direct = _integer(tags.get("rotate"))
    if direct is not None:
        return direct % 360
    for item in stream.get("side_data_list", []):
        if isinstance(item, dict):
            side_data_rotation = _integer(item.get("rotation"))
            if side_data_rotation is not None:
                return side_data_rotation % 360
    return None


def _dynamic_range(stream: dict[str, Any]) -> str | None:
    transfer = str(stream.get("color_transfer") or "").casefold()
    if transfer in {"smpte2084", "arib-std-b67"}:
        return "HDR"
    if transfer:
        return "SDR"
    return None


class FfprobeAdapter:
    """Extract video and audio metadata through ffprobe without a shell."""

    extractor_name = "FFPROBE"

    def __init__(self, command: str, timeout_seconds: int, panorama_threshold: float):
        self.command = command
        self.timeout_seconds = timeout_seconds
        self.panorama_threshold = panorama_threshold

    def status(self) -> ToolStatus:
        """Inspect ffprobe availability and version."""
        return inspect_tool("ffprobe", self.command, ["-version"])

    def extract(self, path: Path, status: ToolStatus) -> AdapterExtraction:
        """Extract complete stream and format JSON and normalize V1 fields."""
        if not status.available:
            raise ExternalToolError(status.error or "ffprobe is unavailable.")
        try:
            completed = subprocess.run(
                [
                    status.command,
                    "-v", "error",
                    "-show_format",
                    "-show_streams",
                    "-show_chapters",
                    "-print_format", "json",
                    str(path),
                ],
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ExternalToolError(f"ffprobe execution failed: {exc}") from exc
        if completed.returncode != 0:
            message = completed.stderr.strip() or f"Exited with code {completed.returncode}."
            raise ExternalToolError(f"ffprobe failed: {message}")
        try:
            raw = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise ExternalToolError("ffprobe returned invalid JSON.") from exc
        if not isinstance(raw, dict):
            raise ExternalToolError("ffprobe returned an unexpected JSON document.")

        streams = raw.get("streams") if isinstance(raw.get("streams"), list) else []
        video = next((item for item in streams if item.get("codec_type") == "video"), {})
        audio = next((item for item in streams if item.get("codec_type") == "audio"), {})
        file_format = raw.get("format") if isinstance(raw.get("format"), dict) else {}
        rotation = _rotation(video)
        width = _integer(video.get("width"))
        height = _integer(video.get("height"))
        geometry = derive_geometry(width, height, rotation, None, self.panorama_threshold)
        duration = _decimal(file_format.get("duration") or video.get("duration"))
        average_rate = _rate(video.get("avg_frame_rate"))
        real_rate = _rate(video.get("r_frame_rate"))
        variable = None
        if average_rate is not None and real_rate is not None:
            variable = abs(average_rate - real_rate) > 0.001
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
            duration_ms=int(duration * 1000) if duration is not None else None,
            container=_text(file_format.get("format_name")),
            video_codec=_text(video.get("codec_name")),
            audio_codec=_text(audio.get("codec_name")),
            bitrate_bps=_integer(file_format.get("bit_rate") or video.get("bit_rate")),
            frame_rate=average_rate,
            is_variable_frame_rate=variable,
            rotation_degrees=rotation,
            dynamic_range=_dynamic_range(video),
            audio_sample_rate_hz=_integer(audio.get("sample_rate")),
            audio_channels=_integer(audio.get("channels")),
            stream_count=len(streams),
            color_space=_text(video.get("color_space")),
        )
        return AdapterExtraction(raw_metadata=raw, normalized=normalized)


def _text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    return str(value)
