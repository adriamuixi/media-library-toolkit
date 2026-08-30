# Filesystem Scan

## Purpose

Build a basic SQLite inventory of a registered source without opening, hashing, or modifying media content.

## Input

- An initialized TEST or PRODUCTION catalog.
- A registered logical library.
- A registered provenance source within that library.
- An existing physical root directory.
- A media filter: `photos`, `videos`, or `all`.

The supplied root represents the complete runtime root for that scan. It is never stored as portable file identity.

## Output

The scanner records:

- source-relative path;
- current filename and original filename;
- lowercase extension;
- basic type: `PHOTO`, `VIDEO`, `SIDECAR`, or `UNKNOWN`;
- file size in bytes;
- filesystem modified, changed, and optional birth timestamps;
- stable media and location UUIDs;
- first and last scan references;
- scan arguments, software version, counts, status, and errors.

## Safety

The scanner is READ ONLY with respect to source media. It uses directory traversal and non-following filesystem `stat` calls. It does not open media content, write sidecars, create thumbnails, calculate hashes, rename files, move files, or delete files.

Catalogs, logs, reports, caches, and workspace directories must remain outside the media root. The command rejects unsafe path configurations before creating its log file.

Symbolic links are recorded as warnings and never followed. Hidden entries are skipped unless explicitly included.

## Parameters

```text
--library NAME
--source NAME
--root PATH
--media-type photos|videos|all
--include-hidden
--resume [SCAN_ID]
```

Global `--config` and `--profile` options must appear before `scan`.

## Example

```bash
media --profile test scan \
  --library "Personal Media" \
  --source "Synthetic Camera" \
  --root "/Volumes/SMALL_TEST_LIBRARY" \
  --media-type all
```

## Performance

Traversal and inventory persistence are streaming. The scanner does not load the complete file collection into memory. SQLite work is committed in configurable batches, defaulting to 500 processed entries.

## Idempotency

The tuple of registered source and exact relative path identifies an observed location during the scan phase. Repeating a scan updates that location and preserves its `media_id`. It does not create duplicate rows.

Content identity is not inferred from path. SHA-256 establishes exact logical content identity, while every path remains an independent immutable observation. Conservative movement reconciliation remains a later phase.

## Resume

Every processed entry receives a temporary checkpoint in the same transaction as its inventory change and scan counters. If execution stops, committed checkpoints remain available.

Resume the latest interrupted scan matching all supplied inputs:

```bash
media --profile test scan \
  --library "Personal Media" \
  --source "Synthetic Camera" \
  --root "/Volumes/SMALL_TEST_LIBRARY" \
  --media-type all \
  --resume
```

Resume a specific scan:

```bash
media --profile test scan \
  --library "Personal Media" \
  --source "Synthetic Camera" \
  --root "/Volumes/SMALL_TEST_LIBRARY" \
  --media-type all \
  --resume 00000000-0000-0000-0000-000000000000
```

The library, source, resolved root, media filter, and hidden-entry policy must match the original scan. A completed scan cannot be resumed.

Previously checkpointed files are verified with size and modified time. Changed or disappeared checkpointed entries cause conservative refusal; start a new scan to catalog the new source state. New entries that were not previously checkpointed may be included safely.

Checkpoints are removed when the scan completes. They are processing state, not permanent catalog history.

## Error Handling

Permission failures, unreadable entries, unsupported filesystem objects, and skipped symbolic links are recorded in `scan_error`. An individual traversal problem does not stop the remaining scan. Critical catalog failures terminate the scan and set its status to `FAILED` when possible.

## Known Limitations

- Missing-file reconciliation is intentionally deferred to avoid false missing states during filtered scans.
- Classification uses extensions only; metadata validation comes later.
- The scan root is expected to represent the complete runtime source root.
