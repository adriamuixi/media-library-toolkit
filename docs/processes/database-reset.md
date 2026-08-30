# Database Reset

## Purpose

Discard all analysis and catalog records in a disposable TEST database and immediately recreate an empty current schema.

## Input

- A configuration profile whose environment is `TEST`.
- An optional existing toolkit catalog marked internally as `TEST`.
- Explicit `--confirm-reset` confirmation.

## Output

- A newly initialized TEST catalog.
- A new database ID.
- A per-run external log.

## Safety

The command refuses production profiles, production database markers, invalid database files, missing confirmation, and environment mismatches. It does not inspect or modify media.

## Example

```bash
media --profile test db reset --confirm-reset
```

## Known Limitations

Production catalog reset is intentionally unavailable. Use `media db backup --output PATH` for catalog backups; production recovery procedures remain deliberately conservative.
