SELECT media_id, current_relative_path, original_relative_path, source_name, import_batch
FROM media_with_provenance
WHERE media_status = 'MISSING'
ORDER BY current_relative_path;
