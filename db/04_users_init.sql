--создание таблицы пользователей
create table if not exists users(
     uuid uuid primary key default gen_random_uuid(),
     username varchar(255) not null unique,
     password varchar(255) not null,
     role user_role not null default 'user'
);

insert into users (username, password, role) values ('admin', 'root', 'admin');