from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class Camera(BaseModel):
    camera_id: Optional[UUID] = None
    name: str
    location: str
    rtsp_url: Optional[str] = None
    status: bool = True
