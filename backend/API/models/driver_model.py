from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class Driver(BaseModel):
    driver_id: Optional[UUID] = None
    name: str
    second_name: str
    surname: str
    iin: str
    phone_number: str
    address: str
