from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class Camera(BaseModel):
    camera_id: Optional[UUID] = None
    name: str
    location: str
    status: bool = True
