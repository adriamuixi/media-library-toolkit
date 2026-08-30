SELECT substr(effective_capture_local, 1, 4) AS capture_year, COUNT(*) AS photo_count
FROM media_with_provenance
WHERE media_type = 'PHOTO' AND date_status = 'RESOLVED'
GROUP BY capture_year
ORDER BY capture_year;
