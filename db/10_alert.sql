CREATE TABLE IF NOT EXISTS alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id       UUID REFERENCES drivers(driver_id),
    plate_id        UUID REFERENCES plates(plate_id),
    detection_id    UUID NOT NULL REFERENCES detections(detection_id),
    alert_type      alert_type NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);