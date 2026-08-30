SELECT source_type, source_name, COUNT(*) AS observation_count
FROM media_with_provenance
GROUP BY source_type, source_name
ORDER BY source_type, source_name;
