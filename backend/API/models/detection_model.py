from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class Detection(BaseModel):
    detection_id: Optional[UUID] = None
    camera_id: UUID
    detection_time: datetime
    plates_photo_url: Optional[str] = None
    full_photo_url: Optional[str] = None