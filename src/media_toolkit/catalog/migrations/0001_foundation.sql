CREATE TABLE catalog_metadata (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    database_id TEXT NOT NULL UNIQUE,
    profile_name TEXT NOT NULL,
    environment TEXT NOT NULL CHECK (environment IN ('TEST', 'PRODUCTION')),
    created_at TEXT NOT NULL
);

CREATE TABLE library (
    library_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    environment TEXT NOT NULL CHECK (environment IN ('TEST', 'PRODUCTION')),
    description TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (name, environment)
);

CREATE TABLE source (
    source_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES library(library_id),
    name TEXT NOT NULL,
    source_type TEXT NOT NULL,
    default_timezone TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (library_id, name)
);

CREATE TABLE scan (
    scan_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES library(library_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    root_path_snapshot TEXT NOT NULL,
    status TEXT NOT NULL,
    software_version TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    discovered_count INTEGER NOT NULL DEFAULT 0,
    updated_count INTEGER NOT NULL DEFAULT 0,
    skipped_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_scan_library_started_at ON scan(library_id, started_at);
CREATE INDEX idx_scan_source_started_at ON scan(source_id, started_at);
