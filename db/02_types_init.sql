-- создание типа данных для ролей пользователей
create type user_role as enum ('admin', 'user');

-- таблица алертов (штрафники / угон)
CREATE TYPE alert_type AS ENUM ('wanted', 'stolen');