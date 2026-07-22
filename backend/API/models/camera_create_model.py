from pydantic import BaseModel


class CameraCreate(BaseModel):
    name: str
    location: str
    rtsp_url: str
