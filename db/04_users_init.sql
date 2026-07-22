-- создание таблицы пользователей
create table if not exists users(
     uuid uuid primary key default gen_random_uuid(),
     username varchar(255) not null unique,
     hashed_password varchar(255) not null,
     role user_role not null default 'operator',
     is_active boolean not null default true
);

-- начальный администратор (пароль 'root' — будет захэширован при первом старте API)
insert into users (username, hashed_password, role) values ('admin', 'root', 'admin');
