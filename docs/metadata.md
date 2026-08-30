# Media Metadata

## Purpose

The metadata phase extracts normalized, queryable properties while preserving the original extractor response for traceability. ExifTool handles photographs and ffprobe handles videos.

## Image Geometry

The catalog will store:

- `stored_width_px` and `stored_height_px`: encoded dimensions in pixels;
- `display_width_px` and `display_height_px`: dimensions after applying rotation;
- `size_bytes`: physical file size;
- `megapixels`: derived as width multiplied by height divided by 1,000,000;
- `aspect_ratio`: the longer normalized dimension divided by the shorter one;
- `orientation_class`: `LANDSCAPE`, `PORTRAIT`, `SQUARE`, or `UNKNOWN`;
- `is_panorama`: queryable boolean classification;
- `panorama_reason`: the evidence or rule used for classification;
- `projection_type`: authoritative projection metadata when available.

Dimensions must respect metadata orientation. A photograph stored as 4032 by 3024 pixels with a rotation marker may have normalized display dimensions of 3024 by 4032 pixels.

## Panorama Classification

Classification uses two levels of evidence:

1. The orientation-normalized display width must meet the configured minimum width.
2. Authoritative panorama or projection metadata produces `is_panorama = true` and records the metadata source when the width requirement is met.
3. When authoritative metadata is absent, a configurable aspect-ratio threshold may classify an image as panoramic when the width requirement is met.

The default ratio threshold is `4.0`, evaluated as the longer display dimension divided by the shorter display dimension. A ratio of exactly 4:1 qualifies. The default minimum display width is `2000` pixels. The ratio rule supports both horizontal and vertical shapes, while the width requirement always applies to the orientation-normalized display width.

Example reasons include:

```text
PROJECTION_METADATA
ASPECT_RATIO_THRESHOLD
BELOW_MINIMUM_WIDTH
MANUAL_REVIEW
NOT_PANORAMIC
UNKNOWN_DIMENSIONS
```

The threshold must be stored in configuration and the analysis input signature so a later configuration change can invalidate and recompute the classification safely.

## Video and Audio Fields

Video normalization stores duration as integer milliseconds, container names, video and audio codecs, bitrate, average frame rate, variable-frame-rate state, rotation, dynamic range, audio sample rate, audio channel count, stream count, and color space when ffprobe reports them.

## Raw Data and Cache

Each attempt creates a `metadata_extraction` record. Successful attempts retain the complete JSON response; failures retain a concise error type and message. The current normalized result is separately queryable in `media_metadata`.

A successful result is reused only when all of the following match:

- media identity and extractor;
- extractor version;
- cataloged file size and modification time;
- parser version and panorama threshold.

`media metadata --force` deliberately bypasses this cache. A file whose current size or modification time differs from the scan inventory is refused until another scan updates the catalog.

## Safety

Metadata extraction and panorama classification are READ ONLY with respect to original media. Results are written only to the external SQLite catalog, logs, reports, and cache.
