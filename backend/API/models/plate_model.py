from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class Plate(BaseModel):
    plate_id: Optional[UUID] = None
    plate_number: str
    driver_id: UUID

    def __init__(self, plate_number: str, driver_id: UUID, plate_id: Optional[UUID] = None):
        super().__init__(plate_id=plate_id, plate_number=plate_number, driver_id=driver_id)
