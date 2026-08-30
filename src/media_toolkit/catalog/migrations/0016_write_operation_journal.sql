CREATE TABLE write_operation (
    operation_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES organization_plan(plan_id),
    strategy TEXT NOT NULL CHECK (strategy IN ('COPY', 'MOVE')),
    status TEXT NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED')),
    source_root TEXT NOT NULL,
    destination_root TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    failure_message TEXT
);

CREATE TABLE write_operation_event (
    event_id TEXT PRIMARY KEY,
    operation_id TEXT NOT NULL REFERENCES write_operation(operation_id),
    plan_item_id TEXT REFERENCES organization_plan_item(plan_item_id),
    event_type TEXT NOT NULL CHECK (
        event_type IN ('OPERATION_STARTED', 'ITEM_VERIFIED', 'ITEM_COPIED', 'OPERATION_COMPLETED', 'OPERATION_FAILED')
    ),
    details_json TEXT NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX idx_write_operation_plan ON write_operation(plan_id, started_at DESC);
CREATE INDEX idx_write_operation_event_operation ON write_operation_event(operation_id, recorded_at);

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
