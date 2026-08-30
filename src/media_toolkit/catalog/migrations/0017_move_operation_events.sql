CREATE TABLE write_operation_event_new (
    event_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES write_operation(operation_id),
    plan_item_id TEXT REFERENCES organization_plan_item(plan_item_id),
    event_type TEXT NOT NULL CHECK (
        event_type IN (
            'OPERATION_STARTED', 'ITEM_VERIFIED', 'ITEM_COPIED',
            'ITEM_SOURCE_REMOVED', 'OPERATION_COMPLETED', 'OPERATION_FAILED'
        )
    ),
    details_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

INSERT INTO write_operation_event_new (
    event_id, operation_id, plan_item_id, event_type, details_json, recorded_at
)
SELECT event_id, operation_id, plan_item_id, event_type, details_json, recorded_at
FROM write_operation_event;

DROP TABLE write_operation_event;
ALTER TABLE write_operation_event_new RENAME TO write_operation_event;

CREATE INDEX idx_write_operation_event_operation
    ON write_operation_event(operation_id, recorded_at);

CREATE TRIGGER prevent_write_operation_event_update
BEFORE UPDATE ON write_operation_event
BEGIN
    SELECT RAISE(ABORT, 'Write operation journal events are append-only.');
END;

CREATE TRIGGER prevent_write_operation_event_delete
BEFORE DELETE ON write_operation_event
BEGIN
    SELECT RAISE(ABORT, 'Write operation journal events cannot be deleted.');
END;
