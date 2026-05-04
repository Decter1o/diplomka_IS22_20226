from typing import Optional, List
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
                    return self._row_to_alert(row)
        except Exception as e:
            self.conn.rollback()
            print(f"AlertRepository.create error: {e}")
        return None

    def get_all(self, limit: int = 100, offset: int = 0) -> List[Alert]:
        """Возвращает список алертов, свежие первыми."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, driver_id, plate_id, detection_id, alert_type, created_at
                    FROM alerts
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset)
                )
                return [self._row_to_alert(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"AlertRepository.get_all error: {e}")
        return []

    def get_by_type(self, alert_type: AlertType, limit: int = 100, offset: int = 0) -> List[Alert]:
        """Возвращает алерты конкретного типа."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, driver_id, plate_id, detection_id, alert_type, created_at
                    FROM alerts
                    WHERE alert_type = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (alert_type.value, limit, offset)
                )
                return [self._row_to_alert(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"AlertRepository.get_by_type error: {e}")
        return []

    @staticmethod
    def _row_to_alert(row) -> Alert:
        return Alert(
            id=row[0],
            driver_id=row[1],
            plate_id=row[2],
            detection_id=row[3],
            alert_type=row[4],
            created_at=row[5],
        )