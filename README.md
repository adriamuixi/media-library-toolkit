# Media Library Toolkit

Media Library Toolkit is a local, safety-first command-line application for building a durable catalog of personal photographs and videos. It is designed for large libraries, repeatable imports, exact duplicate detection, traceable naming, and controlled year-based organization.

The project is being built incrementally. The current release contains the Foundation layer: configuration, logging, an installable CLI, a versioned SQLite catalog, isolated test and production profiles, and a guarded test-catalog reset.

## Safety

Original media is read-only by default. No command may delete, move, rename, overwrite, or modify original media unless it belongs to an explicitly reviewed WRITE workflow.

The current Foundation commands do not inspect or modify media files.

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
- ExifTool for a later metadata phase
- ffprobe for a later video metadata phase

ExifTool and ffprobe are not required for the current Foundation commands.

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
