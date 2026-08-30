# ADR-004: Store Image Geometry and Panorama Classification

- Status: Accepted
- Date: 2026-08-30

## Context

Image dimensions and panoramic shape are useful for catalog searches, reports, review screens, and future organization without requiring repeated metadata extraction.

## Decision

Store normalized display width and height, file size, derived megapixels, aspect ratio, orientation class, a panorama flag, its classification reason, and authoritative projection metadata when available.

Use authoritative panorama metadata first. Otherwise use a configurable aspect-ratio rule. The initial proposed threshold is 2.0 and applies to horizontal and vertical images.

## Consequences

Panorama searches remain inexpensive SQLite queries. Classification is reproducible because the reason and rule are retained. A changed threshold requires recomputing the derived classification, not extracting all source metadata again.
