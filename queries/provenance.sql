SELECT observation_id, media_id, original_filename, original_relative_path,
       current_relative_path, source_type, source_name, import_batch, sha256
FROM media_with_provenance
ORDER BY original_relative_path;
