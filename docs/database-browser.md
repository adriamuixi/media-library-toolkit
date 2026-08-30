# Local Database Browser

## Purpose

Local Database Browser is a technical inspection tool for the SQLite catalog. It is separate from Local Review and Local Media Browser:

- Local Review presents focused duplicate and date-review workflows.
- Local Media Browser presents photographs and videos.
- Local Database Browser presents tables, rows, relations, saved SQL queries, migrations, and JSON inspection endpoints.

The initial implementation will use Datasette rather than a custom SQL browser. This keeps the maintenance surface small while providing table navigation, filters, pagination, record detail, query execution, and JSON endpoints.

## Safety Boundary

The browser binds only to the loopback address and opens the configured SQLite catalog using Datasette immutable mode. It does not expose edit controls, remote binding, or network access.

Catalog changes remain the responsibility of migrations, CLI commands, and controlled processing services. The browser is an inspection and debugging surface, not an administration console.

## Command

Use the db browse command with an explicit port. It uses the selected profile's configured catalog and generates Datasette query metadata only under the external cache directory. An explicit database path is intentionally not supported.

## Saved Queries

Versioned, schema-aware inspection queries live in the queries directory and are loaded as Datasette canned queries. The initial set covers:

- photographs and videos by effective year;
- exact duplicate groups;
- no-date and suspicious date states;
- source and import-batch distributions;
- provenance records;
- cataloged missing files.

Queries contain SQL only and never personal database contents.

## Focused Views

The catalog exposes two focused SQLite views: media with provenance and duplicate summary. Views evolve with migrations and do not duplicate or replace the normalized catalog tables.
