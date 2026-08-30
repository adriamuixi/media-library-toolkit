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

## Foundation Scope

The current implementation initializes external working directories and a versioned SQLite catalog. It does not scan or modify media.

## Runtime State

Generated state belongs outside media roots:

```text
data/       SQLite catalogs and future processing state
logs/       Per-run logs
reports/    Human-reviewable exports
cache/      Regenerable analysis artifacts
```

All four directories are ignored by Git.
