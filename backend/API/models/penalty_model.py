from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class Penalty(BaseModel):
    penalty_id: Optional[UUID] = None
    driver_id: UUID
    plate_id: UUID
    detection_id: UUID
    amount: Decimal
    issued_date: Optional[datetime] = None
    payment_status: bool = False
