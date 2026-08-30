# Association Detection Process

Complete a scan first. Metadata extraction improves Live Photo matching but is not required for basename rules.

```bash
media associations detect \
  --library "Personal Media" \
  --source "Camera Import"
```

Review all active relations:

```bash
media associations list \
  --library "Personal Media" \
  --source "Camera Import"
```

Use `--type live-photo`, `--type raw-jpeg`, or `--type sidecar` to filter. Add `--include-inactive` only when historical detections are relevant.

The process is catalog-only. It uses the latest successful raw metadata response plus source-relative paths and classifications. It does not access original media or create sidecars.
