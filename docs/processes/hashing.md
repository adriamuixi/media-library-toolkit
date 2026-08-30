# Hashing Process

## Purpose

Calculate SHA-256 content identities for files already present in a completed source inventory. This process is READ ONLY with respect to media and prepares exact-content evidence for later duplicate review.

## Input

The command requires an initialized catalog, an existing library and source, and the same physical source root used to inventory the file locations:

```bash
media hashes calculate \
  --library "Personal Media" \
  --source "iPhone Personal" \
  --root "/Volumes/SMALL_TEST_LIBRARY" \
  --media-type all
```

`--media-type` accepts `photos`, `videos`, or `all`. The default processes all inventoried file types so exact duplicate evidence is available for sidecars and unclassified files as well.

## Processing

Files are selected in deterministic source-relative-path order. Each file is resolved without following symbolic links, checked against its cataloged size and modification timestamp, and read in configured bounded chunks. The operation checks the file signature again after the final chunk before accepting the digest.

An unchanged successful attempt for the same media record, algorithm, size, and modification timestamp is reused. `--force` bypasses this cache and appends a new attempt. Both successes and failures remain immutable audit history in SQLite; `media_hash` only identifies the current successful digest.

## Output

The command prints selected, hashed, cached, error, and byte totals. Current successful values can be inspected without opening media:

```bash
media hashes list \
  --library "Personal Media" \
  --source "iPhone Personal"
```

The list is ordered by normalized source-relative path and includes media type, cataloged size, SHA-256, and completion timestamp.

## Safety and Failure Handling

The process never writes to original media, changes names, updates timestamps, creates sidecars, or creates generated files inside the selected root. A changed, missing, unsafe, or unreadable file produces an immutable error attempt and does not prevent the remaining selected files from being processed. A file that changed after inventory requires a new scan before a digest can be accepted.
