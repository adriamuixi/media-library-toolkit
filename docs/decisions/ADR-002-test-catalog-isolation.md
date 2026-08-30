# ADR-002: Isolate Test and Production Catalogs

- Status: Accepted
- Date: 2026-08-30

## Context

Development requires frequent clean starts, while a real catalog will contain expensive analysis and historical decisions that must not be deleted accidentally.

## Decision

Use separate database files for TEST and PRODUCTION. Store an environment marker inside every catalog. Provide a reset command only for TEST catalogs and require explicit confirmation.

## Consequences

Developers can reset test state quickly. A wrong path or profile is caught by the internal marker. Production reset requires deliberate manual recovery procedures rather than a convenient CLI command.
