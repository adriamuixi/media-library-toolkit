# SQLite Catalog

SQLite is the durable local catalog. Physical paths are not logical media identity, and test data is isolated from production data.

## Foundation Tables

- `schema_version` records every numbered migration, checksum, application time, and software version.
- `catalog_metadata` contains a unique database ID and the TEST or PRODUCTION safety marker.
- `library` represents a logical media library.
- `source` records media provenance independently from runtime mount paths.
- `scan` records traceable scan executions.

## Catalog Registration

Logical libraries and provenance sources must be registered before scanning. Registration uses stable UUID identifiers and is idempotent: an identical repeated registration returns the existing record. A repeated name with different settings is rejected so provenance history is never rewritten implicitly.

Source default timezones use IANA names such as `Europe/Madrid`. A source does not store a permanent filesystem root; the runtime root will be recorded by each scan without becoming portable file identity.

## Scan Inventory Tables

- `media_file` gives each discovered file a stable UUID and stores its current basic classification, size, original filename, discovery timestamps, and catalog status.
- `file_location` stores source-relative paths, a normalized path for conflict analysis, filesystem timestamps, and first/last scan references.
- `scan_error` stores non-fatal warnings and errors with relative paths and processing stages.
- `scan_checkpoint` temporarily stores committed per-entry progress for interrupted-scan recovery.

A repeated scan of the same source-relative path updates the existing `media_file` and `file_location` rows rather than creating duplicates. Path identity is intentionally not treated as content identity.

The current inventory schema precedes logical content identity. The provenance phase will migrate it without discarding records so that a logical content item can reference multiple immutable file observations. `file_location` data must not be collapsed merely because observations share a SHA-256 hash.

Absolute scan roots are retained in `scan.root_path_snapshot` for traceability only. Portable file location queries use `file_location.relative_path`.

Checkpoints are written in the same transaction as inventory changes and progress counters. They remain available while a scan is `RUNNING` or `FAILED` and are deleted transactionally when the scan completes.

## Metadata Tables

- `metadata_extraction` is the immutable history of successful and failed ExifTool or ffprobe attempts. It stores the extractor version, input file signature, normalization configuration signature, raw JSON, and any error.
- `media_metadata` stores the latest successful normalized values for fast queries. These include geometry, panorama state, video duration, codecs, bitrate, frame rate, rotation, dynamic range, audio properties, and selected camera fields.

File size remains on both `media_file` and `file_location` because it belongs to inventory identity and precondition validation. Duration is stored as integer milliseconds in `media_metadata` to avoid floating-point comparison ambiguity.

## Hash Tables

- `hash_attempt` is immutable history for every SHA-256 calculation attempt. It records the cataloged input signature, byte count, timing, digest on success, and structured error information on failure.
- `media_hash` points each current `media_file` record to its latest successful SHA-256 attempt for efficient lookup.

Hashing streams bounded chunks from a validated cataloged path. A cached success is reusable only when the algorithm, cataloged size, and cataloged modification timestamp all match. Hashing records an error and continues with other files when a file is missing, unsafe, changed, or unreadable.

The current hash does not yet create a logical `media_item` or collapse inventory paths. The next duplicate-grouping stage will use equal SHA-256 values as exact-content evidence while retaining every physical observation for the later provenance migration.

Same-size candidate generation is a read-only catalog query. It groups only present files in one library that share a byte size and is intentionally non-authoritative: equal size is a performance filter, not duplicate evidence. SHA-256 equality is required before later duplicate grouping can call content exact.

Exact duplicate grouping is also a read-only catalog query. It includes only present files whose current successful SHA-256 values are equal. It neither selects a preferred physical copy nor changes media, inventory, or historical provenance.

The optional duplicate source-type ranking is configuration only. It may recommend one uniquely highest-ranked member for review, but it does not update SQLite identity, select an operation, or authorize cleanup. An unconfigured or tied group has no recommendation.

## Planned Provenance Tables

The V1 provenance migration will introduce or evolve records for:

- `import_batch`: a stable identifier, source, label, and registration timestamps for one incorporation set;
- `media_item`: logical content identity established by exact SHA-256;
- `file_observation`: every historical appearance of content at a source-relative path;
- current location history: audited transitions without replacing the immutable original path.

Each observation must retain at least its original filename, original relative path, source, import batch, and current relative path when one exists. Optional raw source context is stored independently from any later normalized value and confidence. Multiple observations may reference one logical item, and no duplicate-consolidation process may delete those observations.

Catalog backups use SQLite's consistent online backup mechanism rather than copying an active database file directly. CSV and JSON provenance exports are secondary open-format safeguards, not the catalog of record.

## Capture-Date Tables

- `date_resolution_attempt` retains immutable resolution history, complete candidate evidence as JSON, review reasons, input signatures, local and UTC values, timezone provenance, selected source, and confidence.
- `media_date_resolution` points to the current resolution for fast queries without deleting older attempts.

The local capture value and precision are always kept when a date is selected. UTC is nullable because cameras commonly omit an offset. A source's configured IANA timezone can supply the conversion while remaining visibly identified as source-derived rather than embedded metadata. Date-only evidence is marked explicitly so a storage placeholder cannot be mistaken for a captured midnight time.

## Media Relations

`media_relation` links a primary media record to a companion within the source where the relationship was detected. Relation types are `LIVE_PHOTO_PAIR`, `RAW_JPEG_PAIR`, and `SIDECAR_ASSOCIATION`. Each row stores role details, confidence, detected or conflict status, match method, evidence key, and first and last detection timestamps.

Detection is idempotent. A relationship missing from a later run becomes inactive rather than being deleted, preserving catalog history for future audit and provenance work.

## Migrations

Migrations are ordered SQL files in `src/media_toolkit/catalog/migrations/`. Applied SQL is identified by version and SHA-256 checksum. Editing an already applied migration causes a hard failure; schema changes require a new migration.

SQLite foreign keys, WAL journaling, and full synchronous writes are enabled for writable catalog connections.

## Test Reset

Use:

```bash
media --profile test db reset --confirm-reset
```

The old test catalog is removed and a new catalog is migrated immediately. Production catalogs cannot be reset through this command.
