create table if not exists plates(
    plate_id uuid primary key default gen_random_uuid(),
    plate_number varchar(10) not null,
    driver_id uuid not null references drivers(driver_id)
);

-- Тестовые данные номеров (используются UUIDs из тестовых водителей)
-- Примечание: реальные UUIDs будут автогенерированы при вставке водителей
-- Здесь используются произвольные UUIDs, которые будут переписаны настоящими значениями
-- при реальной работе. Для демонстрации используем LIMIT запросы.

INSERT INTO plates (plate_number, driver_id)
SELECT plate_number, driver_id FROM (
  VALUES
    ('0123BC45', (SELECT driver_id FROM drivers WHERE first_name='Иван' LIMIT 1)),
    ('A123BC99', (SELECT driver_id FROM drivers WHERE first_name='Петр' LIMIT 1)),
    ('123AB45K', (SELECT driver_id FROM drivers WHERE first_name='Марина' LIMIT 1)),
    ('B456CD12', (SELECT driver_id FROM drivers WHERE first_name='Алексей' LIMIT 1)),
    ('789EF67M', (SELECT driver_id FROM drivers WHERE first_name='Елена' LIMIT 1)),
    ('1234BC78', (SELECT driver_id FROM drivers WHERE first_name='Иван' LIMIT 1)),
    ('N910KL34', (SELECT driver_id FROM drivers WHERE first_name='Петр' LIMIT 1))
) AS t(plate_number, driver_id)
WHERE driver_id IS NOT NULL
ON CONFLICT DO NOTHING;