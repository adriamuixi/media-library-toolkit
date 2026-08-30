# ADR-010: Associated Files Are Planning Units

## Status

Accepted.

## Context

Live Photos, RAW/JPEG captures, and sidecars consist of separate physical files that can be broken by independent renaming or organization. Filename matching alone may be ambiguous, while embedded Live Photo identifiers are stronger evidence.

## Decision

The catalog stores explicit typed relations with roles, confidence, evidence method, and conflict status. Metadata identifiers take priority for Live Photos; conservative basename rules cover missing identifiers, RAW/JPEG pairs, and sidecars. Missing relations become inactive rather than being deleted.

Future plans must treat active, non-conflicting relations as indivisible groups and must block or request review for conflicts.

## Consequences

Independent commands can query a stable association model without re-reading media. The system may retain low-confidence candidates and historical inactive detections, increasing catalog size in exchange for safety and traceability.
