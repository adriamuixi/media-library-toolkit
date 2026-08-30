CREATE TABLE import_batch (
    import_batch_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES library(library_id),
    source_id TEXT NOT NULL REFERENCES source(source_id),
    name TEXT NOT NULL,
    description TEXT,
    created_at TEXT NOT NULL,
    UNIQUE (library_id, name)
);

CREATE INDEX idx_import_batch_source_created
    ON import_batch(source_id, created_at);
