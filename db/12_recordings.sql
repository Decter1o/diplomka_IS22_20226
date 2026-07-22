CREATE TABLE IF NOT EXISTS recordings (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    camera_path  VARCHAR(255) NOT NULL,
    minio_object VARCHAR(512) NOT NULL,
    minio_url    TEXT         NOT NULL,
    started_at   TIMESTAMP,
    ended_at     TIMESTAMP,
    duration_sec INTEGER,
    file_size    BIGINT,
    created_at   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recordings_camera_started
    ON recordings (camera_path, started_at DESC);
