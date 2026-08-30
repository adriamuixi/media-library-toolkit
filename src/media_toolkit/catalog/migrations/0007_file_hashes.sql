CREATE TABLE hash_attempt (
    hash_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL REFERENCES media_file(media_id),
    location_id TEXT NOT NULL REFERENCES file_location(location_id),
    algorithm TEXT NOT NULL CHECK (algorithm = 'SHA256'),
    status TEXT NOT NULL CHECK (status IN ('SUCCESS', 'ERROR')),
    digest TEXT,
    input_size_bytes INTEGER NOT NULL,
    input_modified_time_ns INTEGER NOT NULL,
    bytes_hashed INTEGER NOT NULL CHECK (bytes_hashed >= 0),
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL,
    error_type TEXT,
    error_message TEXT,
    CHECK (
        (status = 'SUCCESS' AND length(digest) = 64 AND error_type IS NULL)
        OR
        (status = 'ERROR' AND digest IS NULL AND error_type IS NOT NULL)
    )
);

CREATE TABLE media_hash (
    media_id TEXT PRIMARY KEY REFERENCES media_file(media_id),
    hash_id TEXT NOT NULL REFERENCES hash_attempt(hash_id),
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_hash_attempt_cache
    ON hash_attempt(
        media_id,
        algorithm,
        input_size_bytes,
        input_modified_time_ns,
        status
    );
CREATE INDEX idx_hash_attempt_digest
    ON hash_attempt(algorithm, digest, status);
