# ADR-011: Use a Loopback-Only Read-Only Media Browser

## Status

Accepted and implemented in V1.

## Context

The organized library needs a visual interface that combines physical previews with technical metadata, immutable provenance, duplicate observations, and logical date filters. A browser must remain maintainable and must not expose personal media or bypass controlled WRITE workflows.

## Decision

Implement an optional Flask application using server-rendered HTML, CSS, vanilla JavaScript, read-only SQLite connections, and an external reconstructible thumbnail cache. Bind only to `127.0.0.1` in V1. Resolve content exclusively by media ID with canonical-root and symbolic-link validation. Exclude `toAnalyze` at every query and serving boundary.

Keep Local Media Browser separate from Local Review. Browser V1 has only GET-style viewing operations and no catalog or media mutations.

## Consequences

The core CLI remains lightweight while browser users install a small optional dependency set. The UI can navigate logical months without changing physical year folders and can show missing files from historical catalog data. Remote access, destructive controls, automatic transcoding, and complex frontend tooling remain out of scope.
