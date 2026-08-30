CREATE VIEW media_with_provenance AS
SELECT
    o.observation_id,
    o.media_id,
    o.original_filename,
    o.original_relative_path,
    o.current_relative_path,
    s.source_type,
    s.name AS source_name,
    b.name AS import_batch,
    mi.sha256,
    attempt.status AS date_status,
    attempt.effective_capture_local,
    mf.media_type,
    mf.extension,
    mf.status AS media_status
FROM file_observation AS o
JOIN media_file AS mf ON mf.media_id = o.media_id
JOIN source AS s ON s.source_id = o.source_id
JOIN import_batch AS b ON b.import_batch_id = o.import_batch_id
LEFT JOIN media_item AS mi ON mi.media_item_id = o.media_item_id
LEFT JOIN media_date_resolution AS current ON current.media_id = o.media_id
LEFT JOIN date_resolution_attempt AS attempt ON attempt.resolution_id = current.resolution_id;

CREATE VIEW duplicate_summary AS
SELECT
    mi.media_item_id,
    mi.sha256,
    COUNT(o.observation_id) AS observation_count,
    COUNT(DISTINCT o.source_id) AS source_count
FROM media_item AS mi
JOIN file_observation AS o ON o.media_item_id = mi.media_item_id
GROUP BY mi.media_item_id, mi.sha256
HAVING COUNT(o.observation_id) > 1;
