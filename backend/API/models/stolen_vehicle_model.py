from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class StolenVehicle(BaseModel):
    id: Optional[UUID] = None
    plate_id: UUID
    reported_at: Optional[datetime] = None
    description: Optional[str] = None