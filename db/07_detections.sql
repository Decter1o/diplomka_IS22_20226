create table if not exists detections(
    detection_id     uuid primary key default gen_random_uuid(),
    source_type      varchar(10) not null check (source_type in ('camera', 'video')),
    camera_id        uuid references cameras(camera_id),
    job_id           uuid,
    detection_time   timestamp not null,
    plate_number     varchar(20),
    plates_photo_url varchar(512),
    full_photo_url   varchar(512),
    check (
        (source_type = 'camera' and camera_id is not null and job_id is null) or
        (source_type = 'video'  and job_id is not null and camera_id is null)
    )
);

create index if not exists idx_detections_camera on detections (camera_id) where source_type = 'camera';
create index if not exists idx_detections_video  on detections (job_id)    where source_type = 'video';

-- Тестовые данные детекций
INSERT INTO detections (source_type, camera_id, job_id, detection_time, plate_number, plates_photo_url, full_photo_url)
SELECT
    'camera',
    c.camera_id,
    NULL,
    NOW() - (INTERVAL '1 hour' * (row_number() OVER (ORDER BY c.camera_id) - 1)),
    p.plate_number,
    'https://via.placeholder.com/300x100?text=' || p.plate_number,
    'https://via.placeholder.com/800x600?text=Frame'
FROM cameras c
CROSS JOIN (
    SELECT plate_number FROM plates LIMIT 5
) p
LIMIT 15
ON CONFLICT DO NOTHING;