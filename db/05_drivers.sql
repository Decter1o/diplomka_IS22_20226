create table if not exists drivers(
    driver_id uuid primary key default gen_random_uuid(),
    first_name varchar(255) not null,
    last_name varchar(255) not null,
    iin varchar(12) not null,
    phone_number varchar(11) not null,
    address varchar(255) not null
);

-- Тестовые данные водителей
INSERT INTO drivers (first_name, last_name, iin, phone_number, address) VALUES
('Иван', 'Иванов', '940101123456', '77055551234', 'ул. Толе би, 100'),
('Петр', 'Петров', '951215234567', '77055552345', 'пр. Абая, 200'),
('Марина', 'Сидорова', '960305345678', '77055553456', 'ул. Панфилова, 50'),
('Алексей', 'Козлов', '970420456789', '77055554567', 'ул. Махамбетова, 75'),
('Елена', 'Смирнова', '980530567890', '77055555678', 'пр. Независимости, 300')
ON CONFLICT DO NOTHING;