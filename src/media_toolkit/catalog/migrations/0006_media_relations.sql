CREATE TABLE media_relation (
    relation_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES library(library_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    primary_media_id TEXT NOT NULL REFERENCES media_file(media_id),
    companion_media_id TEXT NOT NULL REFERENCES media_file(media_id),
    relation_type TEXT NOT NULL CHECK (
        relation_type IN ('LIVE_PHOTO_PAIR', 'RAW_JPEG_PAIR', 'SIDECAR_ASSOCIATION')
    ),
    confidence TEXT NOT NULL CHECK (confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    status TEXT NOT NULL CHECK (status IN ('DETECTED', 'CONFLICT')),
    match_method TEXT NOT NULL CHECK (
        match_method IN ('METADATA_IDENTIFIER', 'BASENAME')
    ),
    relation_key TEXT NOT NULL,
    details_json TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    first_detected_at TEXT NOT NULL,
    last_detected_at TEXT NOT NULL,
    CHECK (primary_media_id <> companion_media_id),
    UNIQUE (source_id, relation_type, primary_media_id, companion_media_id)
);

CREATE INDEX idx_media_relation_primary
    ON media_relation(primary_media_id, active);
CREATE INDEX idx_media_relation_companion
    ON media_relation(companion_media_id, active);
CREATE INDEX idx_media_relation_review
    ON media_relation(source_id, relation_type, status, active);
