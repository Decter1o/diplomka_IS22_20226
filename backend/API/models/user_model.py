from enum import Enum
from typing import Optional
from uuid import UUID
from pydantic import BaseModel

class UserRole(str, Enum):
    admin = "admin"
    user = "user"

class User(BaseModel):
    uuid: Optional[UUID] = None
    username: str
    password: str
    role: UserRole = UserRole.user

    def __init__(self, username: str, password: str, role: UserRole = UserRole.user, uuid: Optional[UUID] = None):
        super().__init__(uuid=uuid, username=username, password=password, role=role)
