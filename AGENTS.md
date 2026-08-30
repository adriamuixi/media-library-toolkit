# AGENTS.md

## Project Purpose

Media Library Toolkit is a long-lived, local system for inventorying, cataloging, deduplicating, dating, renaming, and organizing large personal photo and video libraries.

Safety, traceability, portability, and reproducibility take priority over convenience and speed.

## Mandatory Language Rule

All repository content must be written in English, including source code, identifiers, database objects, SQL, comments, docstrings, command output, error messages, configuration, tests, and Markdown documentation.

## Critical Safety Rule

No AI-generated or human-written code may delete, move, rename, overwrite, or modify original media unless the operation is explicitly running in WRITE mode and has passed the documented confirmation and validation barriers.

Analysis commands must never create auxiliary files inside original media directories.

## Operation Modes

- READ ONLY reads media and may write only to external catalogs, logs, caches, and reports.
- DRY RUN creates immutable operation plans without changing media.
- WRITE applies a reviewed plan with explicit confirmation, precondition checks, journaling, and post-operation verification.

WRITE must never be inferred from context or enabled by default.

## Architectural Boundaries

- The CLI parses and validates user intent.
- Application services coordinate independent processing stages.
- Domain rules make deterministic decisions without direct filesystem access.
- Infrastructure adapters access SQLite, the filesystem, ExifTool, and ffprobe.
- Planning code cannot mutate media.
- Media mutation code belongs only in a dedicated operations package.

Physical files, catalog records, and proposed operations are separate concepts.

## Current State

The project is in the Foundation phase. It currently provides:

- an installable Python CLI;
- TOML configuration;
- external logging directories;
- checksum-verified SQLite migrations;
- isolated TEST and PRODUCTION catalog profiles;
- a reset command restricted to catalogs marked as TEST.

Media scanning has not yet been implemented.

## Database Rules

- SQLite is the catalog of record.
- Schema changes use numbered SQL migrations.
- Applied migration checksums may not change.
- Catalogs carry an internal TEST or PRODUCTION marker.
- Test and production data should use separate database files.
- Production catalog reset is not supported by the CLI.
- Absolute runtime roots may be recorded for diagnostics but never used as portable media identity.

## Image Geometry

- Store image width and height in pixels in addition to file size in bytes.
- Derive megapixels and aspect ratio from the normalized dimensions.
- Store orientation as landscape, portrait, square, or unknown.
- Store a queryable panorama flag and the reason that produced it.
- Panorama classification must be deterministic and configurable rather than inferred from filenames.
- Preserve authoritative projection metadata, such as equirectangular or spherical markers, when available.

## Coding Conventions

- Support Python 3.11 and newer.
- Use `pathlib` for paths.
- Prefer the standard library unless a dependency provides clear, documented value.
- Use type hints for public functions and domain models.
- Keep commands independent and resumable where practical.
- Stream large files; never load an entire video into memory.
- Treat individual media errors as reportable failures, not reasons to abort a complete scan.
- Keep deterministic ordering and explicit tie-breakers.
- Preserve user data and unrelated working-tree changes.

## Testing Rules

- Never use a personal media library as a test fixture.
- Use temporary directories and synthetic fixtures.
- Verify that READ ONLY and DRY RUN do not alter media content, paths, sizes, timestamps, or hashes.
- Test every safety barrier and refusal path.
- Controlled WRITE tests may operate only inside temporary test directories.

## Privacy

Never commit personal media, real catalogs, GPS data, private paths, real logs, thumbnails, fingerprints, or local configuration. Keep generated state in ignored directories.

## Scope Discipline

Do not add face recognition, semantic classification, travel detection, events, tags, ratings, cloud integration, or advanced visual/video similarity during V1 Foundation work.

Update `ROADMAP.md`, `CHANGELOG.md`, relevant process documentation, and architectural decisions when behavior changes.
