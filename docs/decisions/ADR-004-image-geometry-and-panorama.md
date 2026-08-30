# ADR-004: Store Image Geometry and Panorama Classification

- Status: Accepted
- Date: 2026-08-30

## Context

Image dimensions and panoramic shape are useful for catalog searches, reports, review screens, and future organization without requiring repeated metadata extraction.

## Decision

Store normalized display width and height, file size, derived megapixels, aspect ratio, orientation class, a panorama flag, its classification reason, and authoritative projection metadata when available.

Require an orientation-normalized display width of at least 2,000 pixels for every panorama classification. After that requirement is met, use authoritative panorama metadata first; otherwise use a configurable aspect-ratio rule. The default threshold is 4.0, inclusive, and applies to horizontal and vertical image shapes.

## Consequences

Panorama searches remain inexpensive SQLite queries. Classification is reproducible because the reason and rule are retained. A changed threshold requires recomputing the derived classification, not extracting all source metadata again.
