# ADR-006: Resume Scans with Transactional Per-Entry Checkpoints

- Status: Accepted
- Date: 2026-08-30

## Context

Large media libraries can require long scans and external disks can disconnect. Restarting all catalog persistence after every interruption wastes time and obscures progress.

## Decision

Store a temporary checkpoint for every processed filesystem entry in the same SQLite transaction as its inventory changes and counters. Resume the same scan ID only when library, source, root, filter, and hidden-entry policy match.

Verify checkpointed regular files by size and modified time. Refuse resume if a processed entry changed or disappeared. Remove checkpoints transactionally when the scan completes.

## Consequences

Committed work is not repeated or double-counted. Interrupted scans retain bounded recovery state in SQLite. Completed scans do not retain redundant checkpoint rows. Resume still traverses directories to validate prior entries, but avoids repeated persistence and creates a consistent audit record.
