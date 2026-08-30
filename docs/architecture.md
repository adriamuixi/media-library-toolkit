# Architecture

## Purpose

The application separates physical storage, catalog knowledge, and proposed operations. This prevents analysis from accidentally becoming mutation and keeps the system understandable as the library and codebase evolve.

## Layers

```text
Command-line interface
        ↓
Application services
        ↓
Deterministic domain rules
        ↓
Infrastructure adapters
        ├── Filesystem
        ├── SQLite
        ├── ExifTool
        └── ffprobe
```

The CLI expresses user intent. Application services coordinate one process at a time. Domain rules resolve dates, names, duplicate preferences, and conflicts. Infrastructure adapters perform external IO.

Planning and execution are separate. A plan describes intended changes; only a dedicated WRITE operation may apply them.

## Identity and Provenance Boundary

The V1 catalog will distinguish logical content from historical observations:

```text
media item identified by exact content
        ├── observation in old disk and original path
        ├── observation in laptop backup and original path
        └── current retained physical location
```

A logical media item can have multiple file observations. Each observation belongs to a source and import batch and retains its immutable original filename, original relative path, and raw folder context. Reorganization changes current-location state through an audited operation; it never rewrites historical provenance.

Reconstructible analysis data, such as hashes, dimensions, codecs, and extracted metadata, is separate from non-reconstructible history, such as original paths, import origin, and manual decisions. Backup policy prioritizes the latter.

## Current Scope

The current implementation initializes external working directories, maintains a versioned SQLite catalog, scans media read-only, extracts metadata read-only, and resolves effective dates from cataloged evidence. It does not modify media.

## Runtime State

Generated state belongs outside media roots:

```text
data/       SQLite catalogs and future processing state
logs/       Per-run logs
reports/    Human-reviewable exports
cache/      Regenerable analysis artifacts
```

All four directories are ignored by Git.
