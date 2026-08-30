# Catalog Registration

## Purpose

Register stable logical libraries and provenance sources before filesystem scanning begins.

## Input

A library requires a name and accepts an optional description. A source requires an existing library, a stable name, a provenance type, and an optional IANA timezone.

Supported initial source types are:

```text
ANDROID
CAMERA
DOWNLOAD
IPHONE
MASTER_LIBRARY
OLD_DISK
SCREENSHOT
TO_ANALYZE
UNKNOWN
WHATSAPP
```

## Output

Registrations are stored in the selected TEST or PRODUCTION SQLite catalog. Every record receives a UUID and UTC creation and update timestamps.

## Safety

Registration does not access or modify media files. The selected catalog must already exist and its internal environment marker must match the selected profile.

Registration is idempotent. Repeating the same command returns `EXISTING`. Reusing a name with different settings is rejected rather than updated implicitly.

## Parameters and Examples

```bash
media --profile test library add "Personal Media" \
  --description "Synthetic development library"

media --profile test source add \
  --library "Personal Media" \
  --name "Synthetic Camera" \
  --type camera \
  --default-timezone Europe/Madrid

media --profile test library list
media --profile test source list --library "Personal Media"
```

Global options such as `--profile` and `--config` must appear before the top-level command.

## Performance

Registration performs indexed single-record lookups and small transactions. It is not performance-sensitive.

## Known Limitations

Records cannot yet be renamed or updated through the CLI. Update operations will require explicit audit behavior before being added.
