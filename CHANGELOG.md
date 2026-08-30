# Changelog

All notable project changes will be documented in this file.

The project intends to follow Semantic Versioning once stable public releases begin.

## [Unreleased]

### Changed

- Changed panorama classification to require a minimum 2,000 px orientation-normalized display width and changed the default geometric threshold from 2:1 to an inclusive 4:1. Authoritative projection metadata takes precedence only after the width requirement is met.

- Refactored Local Media Browser detail pages to display complete catalog-backed identity, location, technical metadata, date, hash, provenance, association, extraction-evidence, and review-decision records in readable sections.

### Added

- Added incremental import-batch summaries and immutable completion verification, including full historical SHA-256 duplicate evidence.

- Added Browser V0: a loopback-only read-only Flask gallery for organized photos with media-ID serving, Unicode-safe `toAnalyze` exclusion, external thumbnails, year filtering, and missing-file detail states.

- Expanded Local Media Browser with video playback and external ffmpeg thumbnails, provenance search and filters, technical detail, duplicate observations, filtered navigation, and keyboard shortcuts.

- Added a loopback-only immutable Datasette Database Browser with versioned inspection queries and focused SQLite views.

- Added an explicitly confirmed controlled COPY operation with provenance checks, SHA-256 verification, append-only journaling, and no-overwrite protection.

- Added SQLite-enforced immutable organization plan content and items with checksum protection.

- Added a Debian and Ubuntu bootstrap installer that creates a virtual environment and installs optional review dependencies.

- Added immutable audited manual date decisions that append catalog evidence without modifying media.

- Added a loopback-only paginated local review interface for exact duplicate groups and date review states.

- Added safe external cached JPEG previews for cataloged photos in Local Review.

- Added deterministic read-only year-or-no-date organization plans with checksums and explicit destination-conflict records.

- Added association-aware organization planning that keeps detected related files in one planned year directory.

- Added explicit plan conflict and association-ambiguity blocking, plus external CSV and JSON plan review exports.

- Added mandatory provenance validation for all future WRITE plans.

- Added append-only current-location history for every historical observation.

- Added exclusive external CSV and JSON exports of immutable provenance records.

- Added SHA-256 logical media items linked to every matching historical observation.

- Added immutable import-batch registration and listing for bounded source incorporations.

- Foundation repository structure.
- Installable `media` command.
- TOML configuration with isolated test and production profiles.
- External per-run logging.
- SQLite catalog bootstrap with checksum-verified migrations.
- Internal TEST and PRODUCTION catalog markers.
- Guarded test-catalog reset and automatic clean reinitialization.
- Initial safety, architecture, database, and process documentation.
- Dependency-free Foundation test suite.
- Documented image geometry and panorama classification requirements for the metadata phase.
- Added idempotent logical library and provenance source registration commands.
- Added deterministic library and source listing commands.
- Added IANA timezone validation for source defaults.
- Added strict catalog environment checks to registration operations.
- Added transactional SQLite connection handling with guaranteed closure.
- Added the READ ONLY `media scan` filesystem inventory command.
- Added relative file locations and stable media identities to SQLite.
- Added photo, video, sidecar, and unknown extension classification.
- Added idempotent rescans with batched SQLite progress persistence.
- Added non-fatal traversal error and warning records.
- Added safeguards that keep generated state outside media roots.
- Added default hidden-entry exclusion and non-following symlink behavior.
- Added transactional scan checkpoints and validated interrupted-scan resume.
- Added `--resume` latest-match selection and explicit `--resume SCAN_ID` selection.
- Added conservative refusal when checkpointed source entries change or disappear.
- Added safe ExifTool and ffprobe discovery with `media tools check`.
- Added the READ ONLY `media metadata` extraction command for photos and videos.
- Added normalized image geometry, duration, codec, stream, camera, and color fields.
- Added deterministic configurable orientation and panorama derivation.
- Added complete raw extractor JSON storage for traceability and future normalization.
- Added metadata caching by extractor version, file size, modification time, and configuration signature.
- Added per-file metadata failures and refusal when media changes after inventory.
- Documented immutable historical provenance as a mandatory V1 feature before physical organization.
- Defined import batches, logical content identity, and multiple historical file observations.
- Added catalog backup and open-format provenance export as prerequisites for production WRITE.
- Added catalog-only effective capture-date resolution for photos and videos.
- Added separate local and UTC capture values with metadata, source, and filesystem timezone provenance.
- Added immutable candidate evidence and cached resolution history.
- Added `RESOLVED`, `SUSPICIOUS`, `CONFLICT`, and `NO_DATE` review states.
- Added conservative filename parsing and opt-in low-confidence filesystem fallback.
- Added future, early-year, contradictory metadata, filesystem-gap, and daylight-saving-time review reasons.
- Added `media dates resolve` and filterable `media dates list` commands.
- Added catalog-only Live Photo detection using metadata identifiers and conservative basename fallback.
- Added deterministic RAW/JPEG and sidecar association rules.
- Added explicit association confidence and conflict states.
- Added idempotent relation refresh with inactive history preservation.
- Added `media associations detect` and filterable `media associations list` commands.
- Added the READ ONLY `media hashes calculate` command with bounded streaming SHA-256 reads.
- Added immutable SHA-256 success and error attempt history plus efficient current-hash lookup.
- Added hash caching by cataloged size and modification-time signature, with opt-in forced recalculation.
- Added per-file hash safety checks before and after reads without media mutation.
- Added `media hashes list` for deterministic current-hash inspection.
- Added media duplicates candidates to list same-size files as non-authoritative exact-duplicate candidates.
- Added media duplicates exact to list present exact-content groups by current SHA-256.
- Added optional source-type priority recommendations for exact duplicate groups, with conservative tie handling.
- Added exclusive external CSV and JSON exports for exact-duplicate review reports.
- Designed a staged V1 Local Media Browser for the organized library.
- Selected an optional Flask, server-rendered HTML, CSS, and vanilla JavaScript architecture.
- Defined loopback-only serving, media-ID path resolution, external thumbnail caching, and unconditional `toAnalyze` exclusion.
