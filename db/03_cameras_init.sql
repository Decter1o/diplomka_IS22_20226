--создание таблицы для хранения информации о камерах
create table if not exists cameras(
     camera_id uuid primary key default gen_random_uuid(),
     name varchar(255) not null,
     location varchar(255) not null,
     status boolean not null default true
);

-- Добавить столбец rtsp_url если его ещё нет
ALTER TABLE cameras ADD COLUMN IF NOT EXISTS rtsp_url VARCHAR(512);

-- Тестовые данные камер
INSERT INTO cameras (name, location, status, rtsp_url) VALUES
('Camera-01', 'ул. Толе би, метро', true, 'rtsp://example.com:554/camera-01'),
('Camera-02', 'ул. Макатаева, ЖД вокзал', true, 'rtsp://example.com:554/camera-02'),
('Camera-03', 'пр. Абая, центр города', true, 'rtsp://example.com:554/camera-03'),
('Camera-04', 'ул. Панфилова, парк', true, 'rtsp://example.com:554/camera-04'),
('Camera-05', 'ул. Махамбетова, EXPO', false, 'rtsp://example.com:554/camera-05')
ON CONFLICT DO NOTHING;
