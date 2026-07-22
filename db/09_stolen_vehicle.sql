-- таблица угнанных автомобилей
CREATE TABLE IF NOT EXISTS stolen_vehicles (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plate_id        UUID NOT NULL UNIQUE REFERENCES plates(plate_id) ON DELETE CASCADE,
    reported_at     TIMESTAMP NOT NULL DEFAULT NOW(),
    description     TEXT
);

-- Тестовые данные угнанных автомобилей
INSERT INTO stolen_vehicles (plate_id, description)
SELECT plate_id, 'Угнано ' || TO_CHAR(NOW() - INTERVAL '5 days', 'DD.MM.YYYY')
FROM plates
WHERE plate_number IN ('0123BC45', 'A123BC99')
LIMIT 2
ON CONFLICT DO NOTHING;