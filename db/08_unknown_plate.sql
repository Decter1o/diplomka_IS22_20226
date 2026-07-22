-- таблица для хранения номеров, не найденных в базе
CREATE TABLE IF NOT EXISTS unknown_plates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plate_number    VARCHAR(10) NOT NULL,
    timestamp       TIMESTAMP NOT NULL,
    camera_id       UUID REFERENCES cameras(camera_id),
    job_id          UUID,
    plates_photo_url VARCHAR(512),
    full_photo_url   VARCHAR(512),
    status          VARCHAR(20) DEFAULT 'unrecognized',
    corrected_plate_number VARCHAR(20)
);

-- Тестовые данные неизвестных номеров
INSERT INTO unknown_plates (plate_number, timestamp, camera_id, plates_photo_url, full_photo_url)
SELECT
    'X' || LPAD((row_number() OVER (ORDER BY c.camera_id))::TEXT, 3, '0') || 'YZ99' as plate_number,
    NOW() - (INTERVAL '30 minutes' * (row_number() OVER (ORDER BY c.camera_id))),
    c.camera_id,
    'https://via.placeholder.com/300x100?text=Unknown',
    'https://via.placeholder.com/800x600?text=Unknown'
FROM cameras c
LIMIT 8
ON CONFLICT DO NOTHING;
 