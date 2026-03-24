create table if not exists penalty(
    penalty_id uuid primary key default gen_random_uuid(),
    driver_id uuid not null references drivers(driver_id),
    plate_id uuid not null references plates(plate_id),
    detection_id uuid not null references detections(detection_id),
    amount numeric not null,
    issued_date timestamp not null default now(),
    payment_status boolean not null default false
);