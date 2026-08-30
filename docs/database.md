# SQLite Catalog

SQLite is the durable local catalog. Physical paths are not logical media identity, and test data is isolated from production data.

## Foundation Tables

- `schema_version` records every numbered migration, checksum, application time, and software version.
- `catalog_metadata` contains a unique database ID and the TEST or PRODUCTION safety marker.
- `library` represents a logical media library.
- `source` records media provenance independently from runtime mount paths.
- `scan` records traceable scan executions. Scanning itself is planned for the next phase.

## Migrations

Migrations are ordered SQL files in `src/media_toolkit/catalog/migrations/`. Applied SQL is identified by version and SHA-256 checksum. Editing an already applied migration causes a hard failure; schema changes require a new migration.

SQLite foreign keys, WAL journaling, and full synchronous writes are enabled for writable catalog connections.

## Test Reset

Use:

```bash
media --profile test db reset --confirm-reset
```

The old test catalog is removed and a new catalog is migrated immediately. Production catalogs cannot be reset through this command.
