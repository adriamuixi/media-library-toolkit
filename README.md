# Media Library Toolkit

Media Library Toolkit is a local, safety-first command-line application for building a durable catalog of personal photographs and videos. It is designed for large libraries, repeatable imports, exact duplicate detection, traceable naming, and controlled year-based organization.

The current release provides read-only inventory scans, metadata extraction, capture-date resolution, media associations, exact SHA-256 analysis, immutable provenance, catalog backups, controlled organization, local review and browsing, and verified incremental import batches.

## Safety

Original media is read-only by default. No command may delete, move, rename, overwrite, or modify original media unless it belongs to an explicitly reviewed WRITE workflow.

Scan and metadata commands inspect files but never modify them.

The `media hashes calculate` command reads cataloged files in bounded chunks, records immutable success or error history in SQLite, and never modifies media content or metadata. It refuses a file whose size or modification timestamp has changed since inventory, or while hashing is in progress.

Historical provenance is immutable catalog data. The catalog retains each original filename, original relative path, source, import batch, source-folder context, current location, and every observed location of exact duplicate content. See [docs/provenance.md](docs/provenance.md).

A Local Media Browser provides a loopback-only, read-only visual gallery over the organized library and SQLite catalog. It includes `no_date`, always excludes `toAnalyze`, caches thumbnails outside media roots, and exposes original provenance without modifying media. See [docs/browser.md](docs/browser.md).

The Local Database Browser is a separate loopback-only, read-only Datasette interface for technical SQLite inspection, saved queries, migrations, and relationships. See [docs/database-browser.md](docs/database-browser.md).

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

On a new Debian or Ubuntu installation, use the bootstrap script. It detects missing Python support packages, and the explicit option installs them before creating an isolated environment:

```bash
git clone https://github.com/adriamuixi/media-library-toolkit.git
cd media-library-toolkit
./scripts/bootstrap.sh --install-system-dependencies
```

The default bootstrap installs the project, development tools, local review interface, Local Media Browser, and local Database Browser. It creates the virtual environment; activate it with:

```bash
source .venv/bin/activate
```

The `media` command is then available:

```bash
media --help
media --version
```

For a core-only setup without development or local-review dependencies:

```bash
./scripts/bootstrap.sh --runtime
```

The bootstrap only invokes `apt-get` when `--install-system-dependencies` is explicitly supplied.

## Start Here

Read the [User Guide](docs/user-guide.md) before processing a personal library. It explains the safe workflow, the purpose of each command, local HTML interfaces, incremental imports, planning, and the explicit WRITE barrier with diagrams and copyable commands.

Moving the Toolkit or its catalog to another computer? Read [Project and Catalog Migration](docs/migration.md). It gives the exact backup, restore, path-reconnection, cache, and validation steps.

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
media db backup --output PATH
media library add
media library list
media source add
media source list
media batch add
media batch list
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
media provenance export
media plan create --library LIBRARY
media plan list --id PLAN_ID
media plan export --id PLAN_ID --output PATH
media review --library LIBRARY --root MEDIA_ROOT --port 8080
media browse --library LIBRARY --root MEDIA_ROOT --port 8080
media web --library LIBRARY --root MEDIA_ROOT
media operations copy --plan PLAN_ID --source-root SOURCE --destination-root DESTINATION --confirm-write PLAN_ID
media operations move --plan PLAN_ID --source-root SOURCE --destination-root DESTINATION --confirm-write PLAN_ID
media db browse --port 8081
```

Use `media COMMAND --help` for command-specific help.

`media browse` is a loopback-only read-only gallery for an organized library. It excludes the `toAnalyze` directory and writes generated thumbnails only under the configured external cache.

Use `media web --library LIBRARY --root MEDIA_ROOT` to launch Browser at port 8080, Database Browser at port 8081, and Local Review at port 8082 together. It opens Browser by default and each HTML interface provides links to the other two. Press Ctrl+C once to stop all three services. Add `--no-open` when launching without a desktop browser.

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
