# Metadata Extraction Process

## Prerequisites

Register the library and source, initialize the selected catalog, and complete a scan for the same source root. Verify external tools with:

```bash
media tools check
```

ExifTool is required for photographs. ffprobe is required for videos. One unavailable tool does not prevent the other media type from being processed, but affected files receive error records.

## Run

```bash
media metadata \
  --library "Personal Media" \
  --source "Camera Import" \
  --root "/media/read-only-import" \
  --media-type all
```

The command selects present photo and video inventory records in deterministic path order. Before invoking an extractor, it verifies that the file is regular, is not a symbolic link, remains under the selected root, and still matches its cataloged size and modification time.

Results are committed in configurable batches. An individual failure is recorded and does not stop later files. Repeating the command reuses identical successful results. Add `--force` to request a new extraction while retaining the previous history.

## Safety Verification

The command passes media paths to external tools as argument-list values without a shell. It does not create sidecars, previews, thumbnails, or other files in the source root. SQLite data and logs must remain outside that root.
