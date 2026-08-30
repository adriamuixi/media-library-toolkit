"""Deterministic geometry and panorama derivation."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Geometry:
    """Normalized display geometry derived from stored dimensions."""

    display_width_px: int | None
    display_height_px: int | None
    megapixels: float | None
    aspect_ratio: float | None
    orientation_class: str
    is_panorama: bool
    panorama_reason: str


def derive_geometry(
    width_px: int | None,
    height_px: int | None,
    rotation_degrees: int | None,
    projection_type: str | None,
    panorama_threshold: float,
    panorama_min_width_px: int,
) -> Geometry:
    """Derive query fields without inventing missing dimensions."""
    if not width_px or not height_px or width_px < 1 or height_px < 1:
        return Geometry(None, None, None, None, "UNKNOWN", False, "UNKNOWN_DIMENSIONS")

    normalized_rotation = None if rotation_degrees is None else rotation_degrees % 360
    if normalized_rotation in {90, 270}:
        display_width, display_height = height_px, width_px
    else:
        display_width, display_height = width_px, height_px

    if display_width > display_height:
        orientation = "LANDSCAPE"
    elif display_height > display_width:
        orientation = "PORTRAIT"
    else:
        orientation = "SQUARE"

    aspect_ratio = max(display_width, display_height) / min(display_width, display_height)
    projection = (projection_type or "").casefold()
    authoritative_panorama = any(
        marker in projection
        for marker in ("equirectangular", "spherical", "cylindrical", "panorama")
    )
    if display_width < panorama_min_width_px:
        is_panorama = False
        panorama_reason = "BELOW_MINIMUM_WIDTH"
    elif authoritative_panorama:
        is_panorama = True
        panorama_reason = "PROJECTION_METADATA"
    elif aspect_ratio >= panorama_threshold:
        is_panorama = True
        panorama_reason = "ASPECT_RATIO_THRESHOLD"
    else:
        is_panorama = False
        panorama_reason = "NOT_PANORAMIC"

    return Geometry(
        display_width_px=display_width,
        display_height_px=display_height,
        megapixels=round((width_px * height_px) / 1_000_000, 6),
        aspect_ratio=round(aspect_ratio, 8),
        orientation_class=orientation,
        is_panorama=is_panorama,
        panorama_reason=panorama_reason,
    )
