from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel
 
 
class UnknownPlate(BaseModel):
    id: Optional[UUID] = None
    plate_number: str
    timestamp: datetime
    camera_id: UUID
    plates_photo_url: Optional[str] = None