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

    def __init__(self, driver_id: UUID, plate_id: UUID, detection_id: UUID, amount: Decimal, issued_date: Optional[datetime] = None, payment_status: bool = False, penalty_id: Optional[UUID] = None):
        super().__init__(penalty_id=penalty_id, driver_id=driver_id, plate_id=plate_id, detection_id=detection_id, amount=amount, issued_date=issued_date, payment_status=payment_status)
