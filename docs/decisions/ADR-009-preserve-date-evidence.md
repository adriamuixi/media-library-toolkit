# ADR-009: Preserve Date Evidence and Uncertainty

## Status

Accepted.

## Context

Media can contain missing, timezone-free, implausible, or contradictory dates. Selecting one value without its evidence makes later correction and review unsafe.

## Decision

Date resolution will preserve every parsed candidate and append immutable attempts. The current record stores local capture time separately from nullable UTC, identifies timezone provenance, and exposes explicit resolved, suspicious, conflict, and no-date states. Filesystem fallback is configurable and disabled by default.

## Consequences

Year planning can use reviewed dates without pretending that uncertain evidence is authoritative. Future manual corrections and HTML review can refer to retained candidates and append audited decisions instead of modifying extractor metadata or media files.
