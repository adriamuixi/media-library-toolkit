CREATE TABLE import_batch_verification (
    verification_id TEXT PRIMARY KEY,
    import_batch_id TEXT NOT NULL REFERENCES import_batch(import_batch_id),
    verified_at TEXT NOT NULL,
    observation_count INTEGER NOT NULL CHECK (observation_count >= 0),
    hashed_count INTEGER NOT NULL CHECK (hashed_count >= 0),
    metadata_count INTEGER NOT NULL CHECK (metadata_count >= 0),
    dated_count INTEGER NOT NULL CHECK (dated_count >= 0),
    historical_duplicate_observation_count INTEGER NOT NULL CHECK (
        historical_duplicate_observation_count >= 0
    ),
    verification_json TEXT NOT NULL,
    UNIQUE (import_batch_id)
);

CREATE TRIGGER prevent_import_batch_verification_update
BEFORE UPDATE ON import_batch_verification
BEGIN
    SELECT RAISE(ABORT, 'Import batch verifications are immutable.');
END;

CREATE TRIGGER prevent_import_batch_verification_delete
BEFORE DELETE ON import_batch_verification
BEGIN
    SELECT RAISE(ABORT, 'Import batch verifications cannot be deleted.');
END;
