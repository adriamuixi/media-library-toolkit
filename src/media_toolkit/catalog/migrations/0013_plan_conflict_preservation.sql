CREATE TABLE organization_plan_item_new (
    plan_item_id TEXT PRIMARY KEY,
    plan_id TEXT NOT NULL REFERENCES organization_plan(plan_id),
    observation_id TEXT NOT NULL REFERENCES file_observation(observation_id),
    media_id TEXT NOT NULL REFERENCES media_file(media_id),
    destination_relative_path TEXT NOT NULL,
    association_group_key TEXT,
    status TEXT NOT NULL CHECK (status IN ('PROPOSED', 'CONFLICT', 'BLOCKED')),
    reason TEXT,
    UNIQUE (plan_id, observation_id)
);

INSERT INTO organization_plan_item_new (
    plan_item_id, plan_id, observation_id, media_id, destination_relative_path,
    association_group_key, status, reason
)
SELECT
    plan_item_id, plan_id, observation_id, media_id, destination_relative_path,
    association_group_key, status, reason
FROM organization_plan_item;

DROP TABLE organization_plan_item;
ALTER TABLE organization_plan_item_new RENAME TO organization_plan_item;

CREATE INDEX idx_organization_plan_item_plan_status
    ON organization_plan_item(plan_id, status);
CREATE INDEX idx_organization_plan_item_destination
    ON organization_plan_item(plan_id, destination_relative_path);
