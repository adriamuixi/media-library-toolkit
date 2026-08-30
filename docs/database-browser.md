# Local Database Browser

## Purpose

Local Database Browser is a technical inspection tool for the SQLite catalog. It is separate from Local Review and Local Media Browser:

- Local Review presents focused duplicate and date-review workflows.
- Local Media Browser presents photographs and videos.
- Local Database Browser presents tables, rows, relations, saved SQL queries, migrations, and JSON inspection endpoints.

The initial implementation will use Datasette rather than a custom SQL browser. This keeps the maintenance surface small while providing table navigation, filters, pagination, record detail, query execution, and JSON endpoints.

## Safety Boundary

The browser will bind only to the loopback address by default and open the configured SQLite catalog in read-only mode. It will not expose edit controls, arbitrary write SQL, remote binding, or network access.

Catalog changes remain the responsibility of migrations, CLI commands, and controlled processing services. The browser is an inspection and debugging surface, not an administration console.

## Planned Command

The database browse command will use the selected profile's configured catalog and accept an explicit port. An explicit database path may be considered later only when it can be validated against the selected profile and the same read-only safeguards.

## Saved Queries

Versioned, schema-aware inspection queries will live in the queries directory. The initial set will cover:

- photographs and videos by effective year;
- exact duplicate groups;
- no-date and suspicious date states;
- source and import-batch distributions;
- provenance records;
- cataloged missing files.

Queries contain SQL only and never personal database contents.

## Focused Views

The implementation may add a minimal number of SQLite views when they materially simplify recurring inspection. Candidate views are media with provenance and duplicate summary. Views must evolve with migrations and must not duplicate or replace the normalized catalog tables.
