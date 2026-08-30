# Media Library Toolkit

Media Library Toolkit is a local, safety-first command-line application for building a durable catalog of personal photographs and videos. It is designed for large libraries, repeatable imports, exact duplicate detection, traceable naming, and controlled year-based organization.

The project is being built incrementally. The current release provides the Foundation layer, read-only inventory scans, cached photo and video metadata extraction, capture-date resolution, media associations, and streaming SHA-256 calculation.

## Safety

Original media is read-only by default. No command may delete, move, rename, overwrite, or modify original media unless it belongs to an explicitly reviewed WRITE workflow.

Scan and metadata commands inspect files but never modify them.

The `media hashes calculate` command reads cataloged files in bounded chunks, records immutable success or error history in SQLite, and never modifies media content or metadata. It refuses a file whose size or modification timestamp has changed since inventory, or while hashing is in progress.

Historical provenance is treated as immutable catalog data. Before physical organization is implemented, the catalog will retain each original filename, original relative path, source, import batch, source-folder context, current location, and every observed location of exact duplicate content. See [docs/provenance.md](docs/provenance.md).

A later V1 Local Media Browser will provide a loopback-only, read-only visual gallery over the organized library and SQLite catalog. It will include `no_date`, always exclude `toAnalyze`, cache thumbnails outside media roots, and expose original provenance without modifying media. See [docs/browser.md](docs/browser.md).

Catalog environments are physically separated by default:

```text
data/production/catalog.sqlite3
data/test/catalog.sqlite3
```

Only a catalog marked internally as `TEST` can be reset by the CLI. Production catalog reset is intentionally unsupported.

See [docs/safety.md](docs/safety.md) for the complete safety model.

## Requirements

- Python 3.11 or newer
- SQLite, provided by Python
- ExifTool for photograph metadata
- ffprobe for video and audio stream metadata

ExifTool and ffprobe are optional for Foundation and scan commands. Check their configured locations with `media tools check` before extracting metadata.

## Installation

Create an isolated environment and install the project in editable mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

The `media` command is then available:

```bash
media --help
media --version
```

The project has no runtime Python dependencies in the Foundation release.

## Quick Start

Initialize a disposable test catalog:

```bash
media --profile test init
media --profile test db status
```

Reset it and immediately recreate a clean schema:

```bash
media --profile test db reset --confirm-reset
```

Initialize the production catalog only when ready:

```bash
media init
media db status
```

Register a logical library and one provenance source:

```bash
media library add "Personal Media" \
  --description "Long-term personal photo and video archive"

media source add \
  --library "Personal Media" \
  --name "iPhone Personal" \
  --type iphone \
  --default-timezone Europe/Madrid

media library list
media source list --library "Personal Media"
```

Registration is idempotent. Repeating an identical command returns the existing record. Reusing a name with conflicting settings fails instead of silently updating catalog history.

Scan a small source in READ ONLY mode:

```bash
media scan \
  --library "Personal Media" \
  --source "iPhone Personal" \
  --root "/Volumes/SMALL_TEST_LIBRARY" \
  --media-type all
```

The scanner stores only paths relative to `--root` as portable file locations. The absolute root is retained only in the scan execution record for diagnostics. Hidden entries and symbolic links are skipped by default.

Resume the latest matching interrupted scan:

```bash
media scan \
  --library "Personal Media" \
  --source "iPhone Personal" \
  --root "/Volumes/SMALL_TEST_LIBRARY" \
  --media-type all \
  --resume
```

Use `--resume SCAN_ID` to select a specific interrupted scan. Resume requires the same library, source, root, media filter, and hidden-entry policy.

After a successful scan, extract metadata:

```bash
media tools check
media metadata \
  --library "Personal Media" \
  --source "iPhone Personal" \
  --root "/Volumes/SMALL_TEST_LIBRARY" \
  --media-type all
```

Successful results are cached by extractor version, cataloged size and modification time, and normalization configuration. Use `--force` only when an intentional re-extraction is required. If a file changed after its scan, metadata extraction records an error and asks for a new scan.

Resolve effective capture dates from cataloged metadata and filename evidence:

```bash
media dates resolve \
  --library "Personal Media" \
  --source "iPhone Personal" \
  --media-type all

media dates list \
  --library "Personal Media" \
  --source "iPhone Personal" \
  --status conflict
```

Resolution never hides uncertainty. Current states are `RESOLVED`, `SUSPICIOUS`, `CONFLICT`, and `NO_DATE`. Filesystem fallback is disabled by default because a copied file's modification time is not reliable capture evidence.

Detect files that must remain together during later planning:

```bash
media associations detect \
  --library "Personal Media" \
  --source "iPhone Personal"

media associations list \
  --library "Personal Media" \
  --source "iPhone Personal"
```

Live Photos prefer matching embedded content identifiers and fall back conservatively to compatible basenames. RAW/JPEG pairs and sidecars use deterministic same-directory basename rules. Ambiguous matches remain explicit `CONFLICT` records.

Calculate exact SHA-256 values after a scan:

```bash
media hashes calculate \
  --library "Personal Media" \
  --source "iPhone Personal" \
  --root "/Volumes/SMALL_TEST_LIBRARY" \
  --media-type all

media hashes list \
  --library "Personal Media" \
  --source "iPhone Personal"
```

Hashing is READ ONLY. Successful unchanged file signatures are reused by default; `--force` creates a new immutable hash-attempt record after reading the file again.

Exact duplicate groups may show a non-destructive preferred member when `[duplicates].source_type_priority` defines a unique preferred source type. An empty list, unknown source types, or tied highest-ranked members remain review cases.

The reset command always refuses a production profile and any database whose internal environment marker is not `TEST`.

## Configuration

Defaults are shown in [`config/default.toml`](config/default.toml). A private configuration can override them:

```bash
media --config config/local.toml --profile test init
```

Relative paths are resolved from the current working directory. `config/local.toml` is ignored by Git.

## Current Commands

```text
media init
media db status
media db reset --confirm-reset
media library add
media library list
media source add
media source list
media scan
media tools check
media metadata
media dates resolve
media dates list
media associations detect
media associations list
media hashes calculate
media hashes list
media duplicates candidates
media duplicates exact
media duplicates report
```

Use `media COMMAND --help` for command-specific help.

## Repository Structure

```text
config/                 Public defaults and private-config examples
docs/                   Architecture, safety, process, and decision records
src/media_toolkit/      Application source code
tests/                  Automated tests using temporary catalogs
examples/               Synthetic, non-personal examples
```

Generated catalogs, logs, reports, caches, thumbnails, and local configuration are excluded from Git.

## Development

Run the dependency-free test suite:

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

The implementation roadmap is maintained in [`ROADMAP.md`](ROADMAP.md).
