SELECT import_batch, source_name, COUNT(*) AS observation_count
FROM media_with_provenance
GROUP BY import_batch, source_name
ORDER BY import_batch, source_name;
