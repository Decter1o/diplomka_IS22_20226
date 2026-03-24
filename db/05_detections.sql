create table if not exists detections(
    detection_id uuid primary key default gen_random_uuid(),
    camera_id uuid not null references cameras(camera_id),
    detection_time timestamp not null
);