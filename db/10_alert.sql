CREATE TABLE IF NOT EXISTS alerts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    driver_id       UUID REFERENCES drivers(driver_id),
    plate_id        UUID REFERENCES plates(plate_id),
    detection_id    UUID NOT NULL REFERENCES detections(detection_id),
    alert_type      alert_type NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Тестовые данные алертов (штрафники)
INSERT INTO alerts (driver_id, plate_id, detection_id, alert_type, created_at)
SELECT
    d.driver_id,
    p.plate_id,
    det.detection_id,
    'wanted'::alert_type,
    NOW() - (INTERVAL '1 hour' * (row_number() OVER (ORDER BY det.detection_id)))
FROM detections det
JOIN plates p ON det.plate_number = p.plate_number
JOIN drivers d ON p.driver_id = d.driver_id
WHERE det.plate_number IN (SELECT plate_number FROM plates LIMIT 3)
LIMIT 5
ON CONFLICT DO NOTHING;

-- Тестовые данные алертов (угоны)
INSERT INTO alerts (driver_id, plate_id, detection_id, alert_type, created_at)
SELECT
    NULL,
    sv.plate_id,
    det.detection_id,
    'stolen'::alert_type,
    NOW() - (INTERVAL '2 hours' * (row_number() OVER (ORDER BY det.detection_id)))
FROM detections det
JOIN stolen_vehicles sv ON det.plate_number = (
    SELECT p.plate_number FROM plates p WHERE p.plate_id = sv.plate_id
)
LIMIT 2
ON CONFLICT DO NOTHING;