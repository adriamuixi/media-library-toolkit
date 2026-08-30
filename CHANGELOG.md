# Changelog

All notable project changes will be documented in this file.

The project intends to follow Semantic Versioning once stable public releases begin.

## [Unreleased]

### Added

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
