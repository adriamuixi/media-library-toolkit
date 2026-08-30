CREATE TABLE observation_location_history (
    observation_location_id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES file_observation(observation_id),
    current_relative_path TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('INITIAL_INVENTORY', 'FUTURE_OPERATION'))
);

CREATE INDEX idx_observation_location_history_current
    ON observation_location_history(observation_id, recorded_at DESC);

INSERT INTO observation_location_history (
    observation_location_id, observation_id, current_relative_path, recorded_at, reason
)
SELECT
    'initial-location-' || observation_id,
    observation_id,
    current_relative_path,
    observed_at,
    'INITIAL_INVENTORY'
FROM file_observation;

CREATE TRIGGER prevent_observation_location_history_update
BEFORE UPDATE ON observation_location_history
BEGIN
    SELECT RAISE(ABORT, 'Observation location history is append-only.');
END;

CREATE TRIGGER prevent_observation_location_history_delete
BEFORE DELETE ON observation_location_history
BEGIN
    SELECT RAISE(ABORT, 'Observation location history cannot be deleted.');
END;
