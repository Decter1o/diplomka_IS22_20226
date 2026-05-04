from datetime import datetime
from typing import Optional, List
from uuid import UUID
from models import unknow_plate_model
from .db import DB


class UnknownPlateRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")

    def create(self, plate_number: str, timestamp: datetime,
               camera_id: UUID, plates_photo_url: Optional[str] = None,
               full_photo_url: Optional[str] = None) -> Optional[unknow_plate_model.UnknownPlate]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO unknown_plates (plate_number, timestamp, camera_id, plates_photo_url)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id, plate_number, timestamp, camera_id, plates_photo_url
                    """,
                    (plate_number, timestamp, str(camera_id), plates_photo_url)
                )
                row = cur.fetchone()
                self.conn.commit()
                if row:
                    return self._row_to_unknown(row)
        except Exception as e:
            self.conn.rollback()
            print(f"UnknownPlateRepository.create error: {e}")
        return None

    def get_all(self, limit: int = 100, offset: int = 0) -> List[unknow_plate_model.UnknownPlate]:
        """Возвращает список неизвестных номеров, свежие первыми."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, plate_number, timestamp, camera_id, plates_photo_url
                    FROM unknown_plates
                    ORDER BY timestamp DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset)
                )
                return [self._row_to_unknown(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"UnknownPlateRepository.get_all error: {e}")
        return []

    @staticmethod
    def _row_to_unknown(row) -> unknow_plate_model.UnknownPlate:
        return unknow_plate_model.UnknownPlate(
            id=row[0],
            plate_number=row[1],
            timestamp=row[2],
            camera_id=row[3],
            plates_photo_url=row[4],
        )