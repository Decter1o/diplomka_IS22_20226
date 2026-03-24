create table if not exists drivers(
    driver_id uuid primary key default gen_random_uuid(),
    name varchar(255) not null,
    second_name varchar(255) not null,
    surname varchar(255) not null,
    iin varchar(12) not null,
    phone_number varchar(11) not null,
    address varchar(255) not null
)