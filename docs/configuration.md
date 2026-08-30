# Configuration

Configuration uses TOML because Python 3.11 can read it without a third-party dependency and because its values and sections are explicit.

Built-in safe defaults match `config/default.toml`. A local file may override any section:

```bash
media --config config/local.toml --profile test init
```

Relative configured paths are resolved from the process working directory. Use absolute paths in personal configuration when commands may be launched from different directories.

`config/local.toml` is ignored by Git.

## Profiles

Profiles isolate runtime catalogs:

```toml
[profiles.production]
database = "./data/production/catalog.sqlite3"
environment = "PRODUCTION"

[profiles.test]
database = "./data/test/catalog.sqlite3"
environment = "TEST"
```

The default profile is production so that ordinary commands never silently operate on test data. During development, always select test explicitly with `--profile test`.

The default media mode is required to remain `read-only`.

## Metadata Rules

The panorama fallback threshold is configurable:

```toml
[metadata]
panorama_aspect_ratio_threshold = 4.0
panorama_min_width_px = 2000
batch_size = 100
timeout_seconds = 60
exiftool_command = "exiftool"
ffprobe_command = "ffprobe"
```

The ratio represents the longer normalized display dimension divided by the shorter dimension and must be greater than 1.0. A panorama must also have an orientation-normalized display width of at least `panorama_min_width_px`. The minimum-width rule applies even when authoritative panorama metadata is present.

The batch size controls SQLite commit frequency during extraction. The timeout applies independently to each external-tool invocation. Commands may be executable names available on `PATH` or explicit executable paths. The application never installs external tools implicitly.

## Scan Settings

```toml
[scan]
include_hidden = false
batch_size = 500
```

Hidden files and directories are excluded by default. The batch size controls how often scan progress and inventory changes are committed to SQLite. A smaller value preserves progress more frequently; a larger value reduces transaction overhead.

Symbolic links are never followed in the current scanner and cannot be enabled through configuration.

## Date Resolution

```toml
[dates]
batch_size = 500
future_tolerance_days = 2
conflict_tolerance_seconds = 86400
suspicious_year_at_or_before = 1980
filesystem_gap_days = 3650
allow_filesystem_fallback = false
```

Date resolution is catalog-only and commits in batches. Tolerances control review flags; they do not rewrite source values. Filesystem fallback is disabled by default because modification and birth times may describe copying or import rather than capture. Enabling it produces low-confidence `SUSPICIOUS` results when no stronger evidence exists.
