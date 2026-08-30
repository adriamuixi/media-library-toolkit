# ADR-007: Preserve Raw Metadata and Cache Normalized Results

## Status

Accepted.

## Context

ExifTool and ffprobe expose many fields whose interpretation can evolve. Re-reading a large media collection is expensive, while storing every extractor field as a dedicated SQLite column would make the schema unstable.

## Decision

Every extraction attempt is recorded with the tool name and version, cataloged file size and modification time, a normalization configuration signature, and its outcome. Successful attempts preserve the complete extractor JSON and update a separate set of stable, queryable normalized columns.

The cache is valid only when the media identity, extractor version, size, modification time, parser version, and relevant configuration match. Forced extraction creates new history instead of overwriting the previous attempt.

## Consequences

Normalization rules can be improved later using retained source data, while frequently queried values remain indexed. The catalog grows more quickly than a normalized-only design, but avoids repeated media access and retains evidence for debugging and migrations.
