--создание таблицы для хранения информации о камерах
create table if not exists cameras(
     uuid uuid primary key default gen_random_uuid(),
     name varchar(255) not null,
     location varchar(255) not null,
     status boolean not null default true
);