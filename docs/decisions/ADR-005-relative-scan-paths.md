# ADR-005: Store Scan Locations Relative to Runtime Roots

- Status: Accepted
- Date: 2026-08-30

## Context

External disks can mount at different absolute paths across computers and operating systems. Absolute paths cannot serve as durable media identity.

## Decision

Store every observed file location relative to the root supplied for its scan. Retain the resolved absolute root only in the scan execution record for diagnostics and traceability.

Normalize a second relative-path value with Unicode NFC and case folding for future conflict analysis, while preserving the exact relative path required to access the file.

## Consequences

The same catalog model remains portable across mount points. Runtime access always combines an explicitly supplied root with the stored relative path. Case and Unicode collisions can be detected without discarding the actual filesystem spelling.
