CREATE TABLE file_observation (
    observation_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL REFERENCES media_file(media_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    original_filename TEXT NOT NULL,
    original_relative_path TEXT NOT NULL,
    current_relative_path TEXT NOT NULL,
    source_context_raw TEXT,
    source_context_normalized TEXT,
    source_context_confidence TEXT CHECK (
        source_context_confidence IN ('HIGH', 'MEDIUM', 'LOW', 'UNKNOWN')
    ),
    observed_at TEXT NOT NULL,
    UNIQUE (source_id, original_relative_path)
);

CREATE INDEX idx_file_observation_media
    ON file_observation(media_id);
CREATE INDEX idx_file_observation_batch
    ON file_observation(import_batch_id);
CREATE INDEX idx_file_observation_current_path
    ON file_observation(source_id, current_relative_path);

INSERT INTO import_batch (
    import_batch_id, library_id, source_id, name, description, created_at
)
SELECT
    'legacy-' || s.source_id,
    s.library_id,
    s.source_id,
    'LEGACY_' || s.source_id,
    'Automatically created while preserving pre-provenance inventory.',
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM source AS s
WHERE NOT EXISTS (
    SELECT 1 FROM import_batch AS b WHERE b.import_batch_id = 'legacy-' || s.source_id
);

INSERT INTO file_observation (
    observation_id,
    media_id,
    source_id,
    import_batch_id,
    original_filename,
    original_relative_path,
    current_relative_path,
    observed_at
)
SELECT
    'legacy-observation-' || fl.location_id,
    fl.media_id,
    fl.source_id,
    'legacy-' || fl.source_id,
    fl.filename,
    fl.relative_path,
    fl.relative_path,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM file_location AS fl;

CREATE TRIGGER prevent_file_observation_original_update
BEFORE UPDATE OF
    media_id,
    source_id,
    import_batch_id,
    original_filename,
    original_relative_path,
    source_context_raw,
    source_context_normalized,
    source_context_confidence,
    observed_at
ON file_observation
BEGIN
    SELECT RAISE(ABORT, 'Historical file observation fields are immutable.');
END;

CREATE TRIGGER prevent_file_observation_delete
BEFORE DELETE ON file_observation
BEGIN
    SELECT RAISE(ABORT, 'Historical file observations cannot be deleted.');
END;
