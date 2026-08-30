CREATE TABLE date_resolution_attempt (
    resolution_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL REFERENCES media_file(media_id),
    extraction_id TEXT REFERENCES metadata_extraction(extraction_id),
    status TEXT NOT NULL CHECK (
        status IN ('RESOLVED', 'SUSPICIOUS', 'CONFLICT', 'NO_DATE')
    ),
    effective_capture_local TEXT,
    effective_capture_at_utc TEXT,
    capture_timezone TEXT,
    timezone_source TEXT NOT NULL CHECK (
        timezone_source IN ('METADATA', 'SOURCE', 'FILESYSTEM', 'UNKNOWN')
    ),
    capture_date_source TEXT,
    capture_date_precision TEXT NOT NULL CHECK (
        capture_date_precision IN ('SECOND', 'DATE', 'UNKNOWN')
    ),
    capture_date_confidence TEXT NOT NULL CHECK (
        capture_date_confidence IN ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN')
    ),
    input_signature TEXT NOT NULL,
    candidates_json TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    resolved_at TEXT NOT NULL
);

CREATE TABLE media_date_resolution (
    media_id TEXT PRIMARY KEY REFERENCES media_file(media_id),
    resolution_id TEXT NOT NULL REFERENCES date_resolution_attempt(resolution_id),
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_date_resolution_cache
    ON date_resolution_attempt(media_id, input_signature);
CREATE INDEX idx_date_resolution_status
    ON date_resolution_attempt(status, capture_date_confidence);
CREATE INDEX idx_date_resolution_local
    ON date_resolution_attempt(effective_capture_local);
