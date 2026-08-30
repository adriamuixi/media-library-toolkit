# ADR-008: Historical Provenance Is Immutable

## Status

Accepted.

## Context

Year-based organization improves the physical library but destroys useful historical folder structure if old paths are retained only on disk. Exact duplicate cleanup can also remove the last physical evidence that identical content appeared in several sources.

## Decision

SQLite will preserve every original file observation, including original filename, original relative path, source, import batch, and raw source context. Exact SHA-256 content identity will allow multiple observations to reference one logical media item. Current-location changes are appended and audited; they do not overwrite original observations.

The catalog will provide consistent backup and open CSV and JSON provenance export before production WRITE is enabled. Provenance will never be embedded into media metadata or generated sidecars.

## Consequences

The catalog can reconstruct origin history after physical consolidation and answer where identical content was observed. Non-reconstructible catalog data requires stronger backup discipline, and future planning and WRITE services must enforce provenance preconditions.
