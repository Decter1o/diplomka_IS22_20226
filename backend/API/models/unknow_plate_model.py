from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class UnknownPlate(BaseModel):
    id: Optional[UUID] = None
    plate_number: str
    timestamp: datetime
    camera_id: Optional[UUID] = None
    job_id: Optional[UUID] = None
    plates_photo_url: Optional[str] = None
    full_photo_url: Optional[str] = None
    status: str = 'unrecognized'
    corrected_plate_number: Optional[str] = None