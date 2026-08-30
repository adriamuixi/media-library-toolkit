# Safety

## Primary Invariant

Original media must not be changed without an explicitly selected WRITE operation.

## Modes

READ ONLY may read original media and write only to external catalogs, logs, reports, and caches. DRY RUN creates operation plans. WRITE applies a previously reviewed plan after explicit confirmation and validation.

No WRITE behavior may be enabled implicitly.

## Catalog Reset

Catalog reset is separate from media WRITE. It deletes catalog knowledge, not media, but is still destructive and guarded.

The reset operation requires all of the following:

1. The selected configuration profile has environment `TEST`.
2. An existing catalog has an internal `TEST` environment marker.
3. The user passes `--confirm-reset`.

The CLI refuses production resets. After a successful reset it immediately creates a new empty catalog with a new database ID and the latest schema.

Test and production catalogs use different files by default. This is safer than mixing test and production rows in one database. The environment is also recorded on the catalog and each library, providing a second visible boundary.

## Future Media Writes

Future copy and move strategies must use immutable plans, source preconditions, destination conflict checks, operation journaling, and post-copy SHA-256 verification. Destination overwrite is prohibited.

## Hashing

`media hashes calculate` is a READ ONLY operation. It validates that generated application state remains outside the media root, rejects symbolic-link paths, streams file content with a configured bounded chunk size, and performs no media mutation.

The operation compares filesystem size and modification time with the completed inventory before it reads a file, then validates the same values after hashing. A mismatch discards the digest, records an immutable error attempt, and requires a new scan. Hashing failures are isolated per file so one unreadable file cannot silently omit the rest of the source.

Duplicate review exports are limited to CSV and JSON catalog reports. The destination must be outside every root recorded for the selected library and must not already exist. Exports list evidence and recommendations only; they never perform physical cleanup.

Before any WRITE operation moves or renames media, it must verify that immutable provenance exists, including the original relative path, source, and import batch. The operation must append a journal record and a current-location transition. It must not replace or delete the only historical reference to an origin.

Production WRITE remains out of scope. The required SQLite backup and open-format provenance export safeguards are implemented and tested; V1.8 must additionally provide reviewed immutable plans, explicit confirmation, journaling, and post-operation verification.

## Planned Local Browser

Local Media Browser is READ ONLY and binds to `127.0.0.1` in V1. It opens SQLite in read-only mode, accepts media IDs rather than paths, validates canonical containment under an explicit organized root, rejects symbolic-link traversal, and never serves `toAnalyze` content. Thumbnails and previews belong to an external reconstructible cache.

The browser must not include media mutation, catalog decision, upload, arbitrary path, directory listing, or remote-bind routes. Missing and changed media produce item-level errors rather than unsafe fallback path resolution.
