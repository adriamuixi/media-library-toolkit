# Media Metadata

## Purpose

The metadata phase will extract normalized, queryable properties while preserving the original extractor response for traceability.

## Image Geometry

The catalog will store:

- `width_px`: normalized display width in pixels;
- `height_px`: normalized display height in pixels;
- `size_bytes`: physical file size;
- `megapixels`: derived as width multiplied by height divided by 1,000,000;
- `aspect_ratio`: the longer normalized dimension divided by the shorter one;
- `orientation_class`: `LANDSCAPE`, `PORTRAIT`, `SQUARE`, or `UNKNOWN`;
- `is_panorama`: queryable boolean classification;
- `panorama_reason`: the evidence or rule used for classification;
- `projection_type`: authoritative projection metadata when available.

Dimensions must respect metadata orientation. A photograph stored as 4032 by 3024 pixels with a rotation marker may have normalized display dimensions of 3024 by 4032 pixels.

## Panorama Classification

Classification will use two levels of evidence:

1. Authoritative panorama or projection metadata produces `is_panorama = true` and records the metadata source.
2. When authoritative metadata is absent, a configurable aspect-ratio threshold may classify an image as panoramic.

The initial proposed ratio threshold is `2.0`, evaluated as the longer display dimension divided by the shorter display dimension. This supports both horizontal and vertical panoramas.

Example reasons include:

```text
PROJECTION_METADATA
ASPECT_RATIO_THRESHOLD
MANUAL_REVIEW
NOT_PANORAMIC
UNKNOWN_DIMENSIONS
```

The threshold must be stored in configuration and the analysis input signature so a later configuration change can invalidate and recompute the classification safely.

## Safety

Metadata extraction and panorama classification are READ ONLY with respect to original media. Results are written only to the external SQLite catalog, logs, reports, and cache.
