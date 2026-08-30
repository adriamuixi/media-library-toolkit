CREATE TABLE media_file (
    media_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES library(library_id),
    original_filename TEXT NOT NULL,
    extension TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (
        media_type IN ('PHOTO', 'VIDEO', 'SIDECAR', 'UNKNOWN')
    ),
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    first_discovered_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PRESENT', 'MISSING'))
);

CREATE TABLE file_location (
    location_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL REFERENCES media_file(media_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    relative_path TEXT NOT NULL,
    normalized_relative_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
    modified_time_ns INTEGER NOT NULL,
    changed_time_ns INTEGER NOT NULL,
    birth_time_ns INTEGER,
    first_seen_scan_id TEXT NOT NULL REFERENCES scan(scan_id),
    last_seen_scan_id TEXT NOT NULL REFERENCES scan(scan_id),
    present INTEGER NOT NULL CHECK (present IN (0, 1)),
    UNIQUE (source_id, relative_path)
);

CREATE TABLE scan_error (
    error_id TEXT PRIMARY KEY,
    scan_id TEXT NOT NULL REFERENCES scan(scan_id),
    relative_path TEXT,
    stage TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('WARNING', 'ERROR')),
    error_type TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at TEXT NOT NULL
);

ALTER TABLE scan ADD COLUMN warning_count INTEGER NOT NULL DEFAULT 0;

CREATE INDEX idx_media_file_library_type
    ON media_file(library_id, media_type);
CREATE INDEX idx_media_file_library_status
    ON media_file(library_id, status);
CREATE INDEX idx_file_location_media
    ON file_location(media_id);
CREATE INDEX idx_file_location_source_present
    ON file_location(source_id, present);
CREATE INDEX idx_file_location_normalized_path
    ON file_location(source_id, normalized_relative_path);
CREATE INDEX idx_scan_error_scan
    ON scan_error(scan_id, severity);
