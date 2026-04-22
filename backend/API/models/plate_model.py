from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class Plate(BaseModel):
    plate_id: Optional[UUID] = None
    plate_number: str
    driver_id: UUID
