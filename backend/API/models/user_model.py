from enum import Enum
from typing import Optional
from uuid import UUID
from pydantic import BaseModel


class UserRole(str, Enum):
    admin = "admin"
    operator = "operator"


class User(BaseModel):
    uuid: Optional[UUID] = None
    username: str
    role: UserRole = UserRole.operator
    is_active: bool = True


class UserCreate(BaseModel):
    username: str
    password: str
    role: UserRole = UserRole.operator
