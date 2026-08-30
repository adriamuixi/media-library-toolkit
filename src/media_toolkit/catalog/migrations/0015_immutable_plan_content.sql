CREATE TRIGGER prevent_organization_plan_content_update
BEFORE UPDATE ON organization_plan
WHEN OLD.library_id <> NEW.library_id
  OR OLD.strategy <> NEW.strategy
  OR OLD.checksum <> NEW.checksum
  OR OLD.created_at <> NEW.created_at
  OR OLD.created_by_version <> NEW.created_by_version
BEGIN
    SELECT RAISE(ABORT, 'Organization plan content is immutable.');
END;

CREATE TRIGGER prevent_organization_plan_item_update
BEFORE UPDATE ON organization_plan_item
BEGIN
    SELECT RAISE(ABORT, 'Organization plan items are immutable.');
END;

CREATE TRIGGER prevent_organization_plan_item_delete
BEFORE DELETE ON organization_plan_item
BEGIN
    SELECT RAISE(ABORT, 'Organization plan items cannot be deleted.');
END;
