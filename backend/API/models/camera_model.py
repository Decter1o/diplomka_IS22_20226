from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class Camera(BaseModel):
    camera_id: Optional[UUID] = None
    name: str
    location: str
    status: bool = True

    def __init__(self, name: str, location: str, status: bool = True, camera_id: Optional[UUID] = None):
        super().__init__(camera_id=camera_id, name=name, location=location, status=status)
