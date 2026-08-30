CREATE TABLE media_item (
    media_item_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE CHECK (length(sha256) = 64),
    created_at TEXT NOT NULL
);

ALTER TABLE file_observation ADD COLUMN media_item_id
    TEXT REFERENCES media_item(media_item_id);

CREATE INDEX idx_file_observation_media_item
    ON file_observation(media_item_id);

INSERT INTO media_item (media_item_id, sha256, created_at)
SELECT
    'sha256-' || attempt.digest,
    attempt.digest,
    strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
FROM media_hash AS current
JOIN hash_attempt AS attempt ON attempt.hash_id = current.hash_id
WHERE attempt.algorithm = 'SHA256' AND attempt.status = 'SUCCESS'
ON CONFLICT(sha256) DO NOTHING;

UPDATE file_observation
SET media_item_id = (
    SELECT 'sha256-' || attempt.digest
    FROM media_hash AS current
    JOIN hash_attempt AS attempt ON attempt.hash_id = current.hash_id
    WHERE current.media_id = file_observation.media_id
)
WHERE EXISTS (
    SELECT 1
    FROM media_hash AS current
    JOIN hash_attempt AS attempt ON attempt.hash_id = current.hash_id
    WHERE current.media_id = file_observation.media_id
      AND attempt.algorithm = 'SHA256'
      AND attempt.status = 'SUCCESS'
);
