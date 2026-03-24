create table if not exists plates(
    plate_id uuid primary key default gen_random_uuid(),
    plate_number varchar(10) not null,
    driver_id uuid not null references drivers(driver_id)
)