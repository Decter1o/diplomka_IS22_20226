from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class Detection(BaseModel):
    detection_id: Optional[UUID] = None
    source_type: Optional[str] = None
    camera_id: Optional[UUID] = None
    job_id: Optional[UUID] = None
    camera_name: Optional[str] = None
    detection_time: datetime
    plate_number: Optional[str] = None
    plates_photo_url: Optional[str] = None
    full_photo_url: Optional[str] = None