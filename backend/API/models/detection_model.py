from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class Detection(BaseModel):
    detection_id: Optional[UUID] = None
    camera_id: UUID
    detection_time: datetime

    def __init__(self, camera_id: UUID, detection_time: datetime, detection_id: Optional[UUID] = None):
        super().__init__(detection_id=detection_id, camera_id=camera_id, detection_time=detection_time)
