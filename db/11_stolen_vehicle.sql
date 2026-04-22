-- таблица угнанных автомобилей
CREATE TABLE IF NOT EXISTS stolen_vehicles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plate_number    VARCHAR(10) NOT NULL UNIQUE,
    reported_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    description     TEXT
);
 