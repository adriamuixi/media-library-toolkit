# ADR-003: Use TOML for Configuration

- Status: Accepted
- Date: 2026-08-30

## Context

Configuration must be readable, typed, portable, and simple to load on a clean installation.

## Decision

Use TOML and Python 3.11 `tomllib`. Keep personal configuration out of Git and allow CLI profile selection.

## Consequences

The Foundation has no runtime Python dependencies. TOML writing, if later required, will need a small dedicated implementation or justified dependency.
