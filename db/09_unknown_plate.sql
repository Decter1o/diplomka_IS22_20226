-- таблица для хранения номеров, не найденных в базе
-- таблица для хранения номеров, не найденных в базе
CREATE TABLE IF NOT EXISTS unknown_plates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plate_number    VARCHAR(10) NOT NULL,
    timestamp       TIMESTAMP NOT NULL,
    camera_id       UUID NOT NULL REFERENCES cameras(camera_id),
    plates_photo_url VARCHAR(512),
    full_photo_url   VARCHAR(512)
);
 