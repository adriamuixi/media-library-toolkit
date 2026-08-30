CREATE TABLE organization_plan (
    plan_id TEXT PRIMARY KEY,
    library_id TEXT NOT NULL REFERENCES library(library_id),
    status TEXT NOT NULL CHECK (status IN ('DRAFT', 'REVIEW_REQUIRED', 'APPROVED', 'APPLIED', 'INVALID')),
    strategy TEXT NOT NULL CHECK (strategy IN ('YEAR_OR_NO_DATE')),
    checksum TEXT NOT NULL UNIQUE CHECK (length(checksum) = 64),
    created_at TEXT NOT NULL,
    created_by_version TEXT NOT NULL
);

CREATE TABLE organization_plan_item (
    plan_item_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES organization_plan(plan_id),
    observation_id TEXT NOT NULL REFERENCES file_observation(observation_id),
    media_id TEXT NOT NULL REFERENCES media_file(media_id),
    destination_relative_path TEXT NOT NULL,
    association_group_key TEXT,
    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'CONFLICT', 'BLOCKED')),
    reason TEXT,
    UNIQUE (plan_id, observation_id),
    UNIQUE (plan_id, destination_relative_path)
);

CREATE INDEX idx_organization_plan_item_plan_status
    ON organization_plan_item(plan_id, status);
