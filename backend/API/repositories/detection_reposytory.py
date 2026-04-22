from datetime import datetime
from typing import Optional
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
               plates_photo_url: Optional[str] = None) -> Optional[detection_model.Detection]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO detections (camera_id, detection_time, plates_photo_url)
                    VALUES (%s, %s, %s)
                    RETURNING detection_id, camera_id, detection_time, plates_photo_url
                    """,
                    (str(camera_id), detection_time, plates_photo_url)
                )
                row = cur.fetchone()
                self.conn.commit()
                if row:
                    return detection_model.Detection(
                        detection_id=row[0],
                        camera_id=row[1],
                        detection_time=row[2],
                        plates_photo_url=row[3],
                    )
        except Exception as e:
            self.conn.rollback()
            print(f"DetectionRepository.create error: {e}")
        return None