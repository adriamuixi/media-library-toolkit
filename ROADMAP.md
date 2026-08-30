# Roadmap

## V0 — Foundation

- [x] Repository structure
- [x] Python packaging and CLI entry point
- [x] TOML configuration
- [x] External logging
- [x] SQLite bootstrap and migration checksums
- [x] Isolated TEST and PRODUCTION catalogs
- [x] Guarded TEST catalog reset
- [x] Foundation tests and documentation

## V1.1 — Scan

- [x] Register libraries and sources
- [ ] Read-only filesystem inventory
- [ ] Relative paths
- [ ] Photo, video, sidecar, and unknown classification
- [ ] Idempotent repeated scans
- [ ] Resume support
- [ ] Per-file error recording

## V1.2 — Metadata

- [ ] ExifTool adapter for photographs
- [ ] ffprobe adapter for videos
- [ ] Image width, height, megapixels, and aspect ratio
- [ ] Derived orientation and panorama classification
- [ ] Normalized metadata
- [ ] Raw extractor response storage
- [ ] Cache invalidation by file signature

## V1.3 — Dates and Associations

- [ ] Effective capture date resolution
- [ ] Confidence and suspicious-date states
- [ ] Timezone handling
- [ ] Live Photo associations
- [ ] RAW and JPEG associations
- [ ] Sidecar associations

## V1.4 — Exact Duplicates

- [ ] Size-based candidate generation
- [ ] Streaming SHA-256
- [ ] Exact duplicate groups
- [ ] Configurable preferred-source ranking
- [ ] Review reports

## V1.5 — Planning

- [ ] Deterministic rename plans
- [ ] Year and `no_date` organization plans
- [ ] Associated-file planning
- [ ] Conflict validation
- [ ] CSV and JSON exports

## V1.6 — Local Review

- [ ] Paginated local HTML interface
- [ ] Pair and group duplicate review
- [ ] Date-conflict and `no_date` review
- [ ] Audited manual decisions
- [ ] Cached previews outside media roots

## V1.7 — Controlled WRITE

- [ ] Immutable checksummed plans
- [ ] Copy and move strategies
- [ ] Copy verification with SHA-256
- [ ] Explicit WRITE confirmation
- [ ] Operation journal
- [ ] Post-operation validation
- [ ] No-overwrite guarantee

## V1.8 — Incremental Imports

- [ ] `toAnalyze` workflow
- [ ] Full historical duplicate comparison
- [ ] Import batch summaries
- [ ] Verified batch completion

## Later Versions

- Photo similarity
- Advanced video similarity
- Month organization
- Integrity validation
- Trips, events, tags, ratings, and semantic cataloging
- Optional external application and cloud integration
