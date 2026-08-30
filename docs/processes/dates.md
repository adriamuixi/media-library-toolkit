# Date Resolution Process

Run metadata extraction first when external tools are available, then resolve dates:

```bash
media dates resolve \
  --library "Personal Media" \
  --source "Camera Import" \
  --media-type all
```

The command reads only SQLite. It does not reopen or modify media. Inputs include the latest successful raw metadata response, original filename, cataloged filesystem timestamps, source timezone, and date configuration.

An unchanged input signature reuses the current result. `--force` appends a new immutable attempt and updates the current pointer without removing history.

Review unresolved records with:

```bash
media dates list \
  --library "Personal Media" \
  --source "Camera Import" \
  --status suspicious
```

Valid filters are `resolved`, `suspicious`, `conflict`, and `no-date`. A later local HTML interface will use these same catalog states for audited manual decisions.
