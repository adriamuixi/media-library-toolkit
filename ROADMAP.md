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
- [x] Read-only filesystem inventory
- [x] Relative paths
- [x] Photo, video, sidecar, and unknown classification
- [x] Idempotent repeated scans
- [x] Resume support
- [x] Per-file error recording

## V1.2 — Metadata

- [x] ExifTool adapter for photographs
- [x] ffprobe adapter for videos
- [x] Image width, height, megapixels, and aspect ratio
- [x] Derived orientation and panorama classification
- [x] Normalized metadata
- [x] Raw extractor response storage
- [x] Cache invalidation by file signature

## V1.3 — Dates and Associations

- [x] Effective capture date resolution
- [x] Confidence and suspicious-date states
- [x] Timezone handling
- [x] Live Photo associations
- [x] RAW and JPEG associations
- [x] Sidecar associations

## V1.4 — Exact Duplicates

- [ ] Size-based candidate generation
- [ ] Streaming SHA-256
- [ ] Exact duplicate groups
- [ ] Configurable preferred-source ranking
- [ ] Review reports

## V1.5 — Immutable Provenance

- [ ] Import batch registration and identity
- [ ] Immutable original filename and relative path
- [ ] Separate logical content from historical file observations
- [ ] Preserve every exact-duplicate observation and source
- [ ] Raw and normalized source context fields
- [ ] Current location tracking without overwriting original location
- [ ] SQLite online backup command
- [ ] Open CSV and JSON provenance exports
- [ ] Provenance preconditions for every future WRITE plan

## V1.6 — Planning

- [ ] Deterministic rename plans
- [ ] Year and `no_date` organization plans
- [ ] Associated-file planning
- [ ] Conflict validation
- [ ] CSV and JSON exports

## V1.7 — Local Review

- [ ] Paginated local HTML interface
- [ ] Pair and group duplicate review
- [ ] Date-conflict and `no_date` review
- [ ] Audited manual decisions
- [ ] Cached previews outside media roots

## V1.8 — Controlled WRITE

- [ ] Immutable checksummed plans
- [ ] Copy and move strategies
- [ ] Copy verification with SHA-256
- [ ] Explicit WRITE confirmation
- [ ] Operation journal
- [ ] Post-operation validation
- [ ] No-overwrite guarantee

## V1.9 — Incremental Imports

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
