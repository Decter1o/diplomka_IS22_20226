from typing import Optional
from uuid import UUID
from models.alert_model import Alert, AlertType
from .db import DB


class AlertRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")

    def create(self, detection_id: UUID, alert_type: AlertType,
               driver_id: Optional[UUID] = None,
               plate_id: Optional[UUID] = None) -> Optional[Alert]:
        """Создаёт алерт. driver_id и plate_id опциональны — для угона могут быть None."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO alerts (driver_id, plate_id, detection_id, alert_type)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, driver_id, plate_id, detection_id, alert_type, created_at
                    """,
                    (
                        str(driver_id) if driver_id else None,
                        str(plate_id) if plate_id else None,
                        str(detection_id),
                        alert_type.value,
                    )
                )
                row = cur.fetchone()
                self.conn.commit()
                if row:
                    return Alert(
                        id=row[0],
                        driver_id=row[1],
                        plate_id=row[2],
                        detection_id=row[3],
                        alert_type=row[4],
                        created_at=row[5],
                    )
        except Exception as e:
            self.conn.rollback()
            print(f"AlertRepository.create error: {e}")
        return None