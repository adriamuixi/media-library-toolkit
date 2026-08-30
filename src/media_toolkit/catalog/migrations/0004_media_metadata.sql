CREATE TABLE metadata_extraction (
    extraction_id TEXT PRIMARY KEY,
    media_id TEXT NOT NULL REFERENCES media_file(media_id),
    location_id TEXT NOT NULL REFERENCES file_location(location_id),
    extractor TEXT NOT NULL CHECK (extractor IN ('EXIFTOOL', 'FFPROBE')),
    extractor_version TEXT,
    status TEXT NOT NULL CHECK (status IN ('SUCCESS', 'ERROR')),
    input_size_bytes INTEGER NOT NULL,
    input_modified_time_ns INTEGER NOT NULL,
    config_signature TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    raw_metadata_json TEXT,
    error_type TEXT,
    error_message TEXT
);

CREATE TABLE media_metadata (
    media_id TEXT PRIMARY KEY REFERENCES media_file(media_id),
    extraction_id TEXT NOT NULL REFERENCES metadata_extraction(extraction_id),
    stored_width_px INTEGER,
    stored_height_px INTEGER,
    display_width_px INTEGER,
    display_height_px INTEGER,
    megapixels REAL,
    aspect_ratio REAL,
    orientation_class TEXT NOT NULL CHECK (
        orientation_class IN ('LANDSCAPE', 'PORTRAIT', 'SQUARE', 'UNKNOWN')
    ),
    is_panorama INTEGER NOT NULL CHECK (is_panorama IN (0, 1)),
    panorama_reason TEXT NOT NULL,
    projection_type TEXT,
    duration_ms INTEGER,
    container TEXT,
    video_codec TEXT,
    audio_codec TEXT,
    bitrate_bps INTEGER,
    frame_rate REAL,
    is_variable_frame_rate INTEGER CHECK (is_variable_frame_rate IN (0, 1)),
    rotation_degrees INTEGER,
    dynamic_range TEXT,
    audio_sample_rate_hz INTEGER,
    audio_channels INTEGER,
    stream_count INTEGER,
    camera_make TEXT,
    camera_model TEXT,
    lens_model TEXT,
    iso INTEGER,
    aperture REAL,
    exposure_time_seconds REAL,
    color_space TEXT,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_metadata_extraction_cache
    ON metadata_extraction(
        media_id,
        extractor,
        extractor_version,
        input_size_bytes,
        input_modified_time_ns,
        config_signature,
        status
    );
CREATE INDEX idx_metadata_extraction_status
    ON metadata_extraction(status, extractor);
CREATE INDEX idx_media_metadata_geometry
    ON media_metadata(display_width_px, display_height_px);
CREATE INDEX idx_media_metadata_duration
    ON media_metadata(duration_ms);
CREATE INDEX idx_media_metadata_panorama
    ON media_metadata(is_panorama, orientation_class);
