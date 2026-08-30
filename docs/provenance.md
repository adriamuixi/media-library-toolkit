# Historical Provenance

## Purpose

Physical organization must never erase where media came from. A file may move from an old folder tree into a year-based library, but SQLite must continue to answer:

- Where is the retained file now?
- What was its original filename?
- What was its original relative path?
- Which source and import batch introduced it?
- Which source-folder context surrounded it?
- In which other paths and sources was the same exact content observed?

Historical provenance is non-reconstructible and immutable. It is more important to protect than analysis values that can be recalculated from media.

## Required Observation Data

Every file observation must retain at least:

```text
original_filename
original_relative_path
current_relative_path
source_type
source_name
import_batch
```

It may also retain:

```text
source_context_raw
source_context_normalized
source_context_confidence
```

`source_context_raw` contains useful original folder context, such as `Old Backup/New Year 2012`. Automated normalization may be added later, but it must write a separate normalized value and never replace the raw value. Folder context is evidence, not an automatic final filename component.

## Import Batches

An import batch identifies one bounded incorporation set, such as:

```text
WD_OLD_2026_08
IPHONE_2027_07
WHATSAPP_2028_01
CANON_SD_2029_04
```

Batch identifiers are stable and unique within a library. Registration records when the batch entered the catalog and which source supplied it. Rescanning a batch must be idempotent.

## Logical Content and Observations

SHA-256 establishes exact content identity. One logical media item may have many historical observations:

```text
Backup1/IMG_001.JPG
OldMac/IMG_001.JPG
USB/IMG_001.JPG
```

If all three hashes match, later planning may retain one physical copy, but all three observations remain in SQLite. Exact duplicate grouping changes neither observation history nor import history.

The implementation should evolve the existing inventory model rather than duplicate it unnecessarily. The required boundary is conceptual and enforceable: content-level facts belong to the logical item; path, source, and batch facts belong to observations.

## Media Metadata Boundary

Provenance is stored only in SQLite. The toolkit must not write it into EXIF, IPTC, XMP, QuickTime metadata, or media containers. It must not create XMP sidecars for provenance.

## Backup and Export

Before production WRITE is available, the CLI must provide a consistent SQLite backup operation, conceptually:

```bash
media database backup
```

It must also export critical provenance to CSV and JSON for inspection and secondary backup. A provenance export should include logical media identity, original and current names and paths, source, import batch, SHA-256 when available, and all historical observations. Exports are not the source of truth and do not replace SQLite backups.

## WRITE Preconditions

Every future move or rename plan must prove that:

1. The affected observation is persisted.
2. Its original relative path is present.
3. Its source and import batch are present.
4. The operation will append a journal entry and current-location transition.
5. No cleanup step will erase the only reference to historical origin.
