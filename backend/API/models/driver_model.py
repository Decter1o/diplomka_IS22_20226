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

    def __init__(self, name: str, second_name: str, surname: str, iin: str, phone_number: str, address: str, driver_id: Optional[UUID] = None):
        super().__init__(driver_id=driver_id, name=name, second_name=second_name, surname=surname, iin=iin, phone_number=phone_number, address=address)
