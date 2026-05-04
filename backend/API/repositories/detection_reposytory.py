from datetime import datetime
from typing import Optional, List
from uuid import UUID
from models import detection_model
from .db import DB


class DetectionRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")

    def create(self, camera_id: UUID, detection_time: datetime,
               plates_photo_url: Optional[str] = None,
               full_photo_url: Optional[str] = None) -> Optional[detection_model.Detection]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO detections (camera_id, detection_time, plates_photo_url, full_photo_url)
                    VALUES (%s, %s, %s, %s)
                    RETURNING detection_id, camera_id, detection_time, plates_photo_url, full_photo_url
                    """,
                    (str(camera_id), detection_time, plates_photo_url, full_photo_url)
                )
                row = cur.fetchone()
                self.conn.commit()
                if row:
                    return self._row_to_detection(row)
        except Exception as e:
            self.conn.rollback()
            print(f"DetectionRepository.create error: {e}")
        return None

    def get_all(self, limit: int = 100, offset: int = 0) -> List[detection_model.Detection]:
        """Возвращает историю детекций, свежие первыми."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT detection_id, camera_id, detection_time, plates_photo_url, full_photo_url
                    FROM detections
                    ORDER BY detection_time DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset)
                )
                return [self._row_to_detection(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"DetectionRepository.get_all error: {e}")
        return []

    @staticmethod
    def _row_to_detection(row) -> detection_model.Detection:
        return detection_model.Detection(
            detection_id=row[0],
            camera_id=row[1],
            detection_time=row[2],
            plates_photo_url=row[3],
            full_photo_url=row[4],
        )