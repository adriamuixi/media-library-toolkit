SELECT * FROM media_with_provenance
WHERE date_status IN ('SUSPICIOUS', 'CONFLICT')
ORDER BY date_status, current_relative_path;
