CREATE TABLE manual_review_decision (
    decision_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL REFERENCES media_file(media_id),
    decision_type TEXT NOT NULL CHECK (
        decision_type IN ('DATE_RESOLUTION', 'DUPLICATE_REVIEW')
    ),
    decision_value_json TEXT NOT NULL,
    reason TEXT NOT NULL,
    decided_at TEXT NOT NULL,
    decided_by TEXT NOT NULL
);

CREATE INDEX idx_manual_review_decision_media
    ON manual_review_decision(media_id, decision_type, decided_at DESC);

CREATE TRIGGER prevent_manual_review_decision_update
BEFORE UPDATE ON manual_review_decision
BEGIN
    SELECT RAISE(ABORT, 'Manual review decisions are immutable.');
END;

CREATE TRIGGER prevent_manual_review_decision_delete
BEFORE DELETE ON manual_review_decision
BEGIN
    SELECT RAISE(ABORT, 'Manual review decisions cannot be deleted.');
END;
