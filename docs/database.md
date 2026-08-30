# SQLite Catalog

SQLite is the durable local catalog. Physical paths are not logical media identity, and test data is isolated from production data.

## Foundation Tables

- `schema_version` records every numbered migration, checksum, application time, and software version.
- `catalog_metadata` contains a unique database ID and the TEST or PRODUCTION safety marker.
- `library` represents a logical media library.
- `source` records media provenance independently from runtime mount paths.
- `scan` records traceable scan executions. Scanning itself is planned for the next phase.

## Catalog Registration

Logical libraries and provenance sources must be registered before scanning. Registration uses stable UUID identifiers and is idempotent: an identical repeated registration returns the existing record. A repeated name with different settings is rejected so provenance history is never rewritten implicitly.

Source default timezones use IANA names such as `Europe/Madrid`. A source does not store a permanent filesystem root; the runtime root will be recorded by each scan without becoming portable file identity.

## Scan Inventory Tables

- `media_file` gives each discovered file a stable UUID and stores its current basic classification, size, original filename, discovery timestamps, and catalog status.
- `file_location` stores source-relative paths, a normalized path for conflict analysis, filesystem timestamps, and first/last scan references.
- `scan_error` stores non-fatal warnings and errors with relative paths and processing stages.

A repeated scan of the same source-relative path updates the existing `media_file` and `file_location` rows rather than creating duplicates. Exact content identity will be added later through streaming SHA-256; path identity is intentionally not treated as content identity.

Absolute scan roots are retained in `scan.root_path_snapshot` for traceability only. Portable file location queries use `file_location.relative_path`.

## Migrations

Migrations are ordered SQL files in `src/media_toolkit/catalog/migrations/`. Applied SQL is identified by version and SHA-256 checksum. Editing an already applied migration causes a hard failure; schema changes require a new migration.

SQLite foreign keys, WAL journaling, and full synchronous writes are enabled for writable catalog connections.

## Test Reset

Use:

```bash
media --profile test db reset --confirm-reset
```

The old test catalog is removed and a new catalog is migrated immediately. Production catalogs cannot be reset through this command.
