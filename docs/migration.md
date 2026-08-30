# Project and Catalog Migration

## Purpose

Use this guide to move Media Library Toolkit to another computer, restore it after a disk replacement, or preserve a catalog before changing environments.

SQLite is the source of truth for catalog identity, provenance, import batches, hashes, duplicate relationships, date evidence, manual decisions, plans, and operation history. Thumbnail caches are reconstructible and are not authoritative.

## What to Transfer

Transfer these items:

1. The repository at a known Git commit or release.
2. A consistent SQLite catalog backup created by `media db backup`.
3. Optional CSV or JSON provenance exports.
4. Your local configuration after reviewing machine-specific paths.
5. The physical media roots, copied independently with your preferred storage migration method.

Do not treat generated thumbnail caches, logs, reports, or temporary state as the only copy of important data.

## Create a Safe Catalog Backup

Stop local web services before migration. Then create a consistent SQLite backup. Do not manually copy an active `catalog.sqlite3` file because its WAL state may be changing.

For a TEST catalog:

```bash
media --profile test db backup \
  --output "/safe-transfer/catalog-test.sqlite3"
```

For a production catalog:

```bash
media db backup \
  --output "/safe-transfer/catalog-production.sqlite3"
```

Create an open provenance export as an additional portable reference:

```bash
media --profile test provenance export \
  --library "Personal Media" \
  --output "/safe-transfer/provenance.csv" \
  --format csv
```

The backup and export destination must be outside every cataloged media root.

## Prepare the New Computer

Clone the repository and install its dependencies:

```bash
git clone https://github.com/adriamuixi/media-library-toolkit.git
cd media-library-toolkit
./scripts/bootstrap.sh --install-system-dependencies
source .venv/bin/activate
```

Use the same Git commit when possible:

```bash
git rev-parse HEAD
```

Copy a local configuration file only if you use one. Review every path because paths are specific to each computer:

```bash
cp /safe-transfer/local.toml config/local.toml
```

Do not commit `config/local.toml` or personal paths to Git.

## Restore the Catalog

Inspect the configured database location first:

```bash
media --profile test db status
```

Copy the backup to that configured location while no Toolkit process is running. For the default TEST profile this is normally:

```text
data/test/catalog.sqlite3
```

For example:

```bash
cp /safe-transfer/catalog-test.sqlite3 data/test/catalog.sqlite3
```

Then validate the restored catalog:

```bash
media --profile test db status
```

Confirm the expected environment, database ID, and schema version. Never replace a production catalog with a TEST backup or the reverse.

## Move or Reconnect Media Roots

Catalog media identity uses relative paths and immutable provenance, not an absolute machine path. When a media disk receives a new mount point, pass the new physical path through `--root`.

For an existing source root on the new computer:

```bash
media --profile test scan \
  --library "Personal Media" \
  --source "Initial Import" \
  --root "/new/path/to/source" \
  --media-type all
```

Run a scan before metadata extraction or hashing if file size or timestamps may have changed during the storage migration.

Open the local interfaces with the new organized-library root:

```bash
media --profile test web \
  --library "Personal Media" \
  --root "/new/path/to/organized-library"
```

## Thumbnail Caches

Thumbnail and preview caches are optional. They live outside media roots and can be deleted or left behind without losing catalog data.

You may copy the cache directory to reduce first-load work, but this is not required. The Browser and Review interfaces regenerate thumbnails safely outside media roots.

## Final Validation Checklist

- [ ] The repository is installed and the intended Git version is checked out.
- [ ] `media db status` reports the expected environment and schema version.
- [ ] The SQLite backup is stored separately from the active catalog.
- [ ] The provenance export is readable.
- [ ] Source and organized media roots are available at the new paths.
- [ ] A new READ ONLY scan completes successfully against each migrated root.
- [ ] Browser, Review, and Database Browser open through `media web`.
- [ ] No WRITE operation is attempted until copied media and provenance have been reviewed.

## Never Do This

- Do not manually copy an active SQLite catalog instead of using `media db backup`.
- Do not place catalog backups, exports, logs, or thumbnail caches inside a media root.
- Do not reset a catalog as a migration method.
- Do not use MOVE before the destination library and its backups have been independently checked.
