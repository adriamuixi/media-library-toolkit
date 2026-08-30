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

The V1 catalog distinguishes logical content from historical observations:

```text
media item identified by exact content
        ├── observation in old disk and original path
        ├── observation in laptop backup and original path
        └── current retained physical location
```

A logical media item can have multiple file observations. Each observation belongs to a source and import batch and retains its immutable original filename, original relative path, and raw folder context. Reorganization changes current-location state through an audited operation; it never rewrites historical provenance.

Reconstructible analysis data, such as hashes, dimensions, codecs, and extracted metadata, is separate from non-reconstructible history, such as original paths, import origin, and manual decisions. Backup policy prioritizes the latter.

## Planned Local Media Browser

The organized-library browser is a separate read-only presentation adapter:

```text
Browser on 127.0.0.1
        ├── read-only SQLite queries
        ├── validated media-ID content resolution
        └── external reconstructible thumbnail cache
```

It will use an optional Flask server with server-rendered HTML, CSS, and small vanilla JavaScript modules. Flask is preferred over FastAPI because the browser does not require a public typed API or an ASGI stack; Flask provides routing, templates, conditional file responses, and a smaller conceptual footprint. The Python standard-library HTTP server is not selected because secure routing, range requests, response headers, and error handling would require custom infrastructure.

The browser is not the Local Review workflow. Local Review is a loopback-only paginated HTML interface for catalog review and may append audited decisions to SQLite. The Local Media Browser exposes no mutation routes and opens SQLite in read-only mode. Shared query and thumbnail components may be reused without combining their permission models.

Local Database Browser is also separate from both interfaces. It will expose the configured SQLite catalog through Datasette in loopback-only read-only mode for technical inspection, schema navigation, saved SQL queries, and debugging. It will not share media-serving routes or mutation controls with Local Review or Local Media Browser.

## Current Scope

The current implementation initializes external working directories, maintains a versioned SQLite catalog, scans media read-only, extracts metadata read-only, resolves effective dates, detects media associations, calculates exact hashes, preserves provenance, and creates read-only organization plans. It does not modify media.

## Runtime State

Generated state belongs outside media roots:

```text
data/       SQLite catalogs and future processing state
logs/       Per-run logs
reports/    Human-reviewable exports
cache/      Regenerable analysis artifacts
```

All four directories are ignored by Git.
