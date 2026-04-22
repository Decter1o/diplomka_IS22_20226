from datetime import datetime
from typing import Optional
from uuid import UUID
from enum import Enum
from pydantic import BaseModel


class AlertType(str, Enum):
    wanted = "wanted"   # штрафник
    stolen = "stolen"   # угнанное авто


class Alert(BaseModel):
    id: Optional[UUID] = None
    driver_id: Optional[UUID] = None   # None для алертов об угоне
    plate_id: Optional[UUID] = None    # None для алертов об угоне
    detection_id: UUID
    alert_type: AlertType
    created_at: Optional[datetime] = None