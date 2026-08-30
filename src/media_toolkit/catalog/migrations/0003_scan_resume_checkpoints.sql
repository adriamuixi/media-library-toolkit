CREATE TABLE scan_checkpoint (
    scan_id TEXT NOT NULL REFERENCES scan(scan_id) ON DELETE CASCADE,
    relative_path TEXT NOT NULL,
    entry_kind TEXT NOT NULL CHECK (
        entry_kind IN ('FILE', 'SKIPPED', 'ISSUE')
    ),
    outcome TEXT NOT NULL,
    size_bytes INTEGER,
    modified_time_ns INTEGER,
    resume_seen INTEGER NOT NULL DEFAULT 1 CHECK (resume_seen IN (0, 1)),
    created_at TEXT NOT NULL,
    PRIMARY KEY (scan_id, relative_path)
);

CREATE INDEX idx_scan_checkpoint_scan_kind
    ON scan_checkpoint(scan_id, entry_kind);
