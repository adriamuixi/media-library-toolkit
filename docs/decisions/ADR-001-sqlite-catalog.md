# ADR-001: Use SQLite as the Local Catalog

- Status: Accepted
- Date: 2026-08-30

## Context

The toolkit needs durable, indexed, transactional state without a server or external service.

## Decision

Use SQLite as the catalog of record and evolve it with small numbered SQL migrations.

## Consequences

The catalog is portable as a single file, works offline, and requires no service administration. Long operations must use batching and appropriate indexes rather than loading complete collections into memory.
