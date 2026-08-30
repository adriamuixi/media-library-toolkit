# Import Batches

Every incorporation workflow registers a stable import batch before scanning or planning physical organization. A batch represents one bounded set from one registered source, not a folder naming convention and not a temporary execution ID.

The batch links every file observation to its import origin. Repeated processing must reuse the same batch identity, while a later acquisition from the same device receives a new batch. Batch provenance remains immutable even when exact duplicate content was already known from another source.

Register and inspect batches with `media batch add` and `media batch list`. Scans accept the registered batch identity and persist it with every historical observation.

The incremental `toAnalyze` workflow requires an import batch, complete read-only scan, metadata extraction, date resolution, SHA-256 calculation, and duplicate comparison against the full historical catalog before completion is recorded. Use these commands after the processing stages:

```bash
media import summary --library "Personal Media" --batch "IPHONE_2027_07"
media import verify --library "Personal Media" --batch "IPHONE_2027_07"
```

Verification refuses empty or incomplete batches. It stores one immutable completion record containing counts for observations, hashes, metadata, date resolutions, and observations whose logical SHA-256 content already appears in another historical batch. It is catalog evidence only; it never moves, copies, renames, deletes, or modifies media.
