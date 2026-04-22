from datetime import datetime
from typing import Optional
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
               camera_id: UUID, plates_photo_url: Optional[str] = None
               ) -> Optional[unknown_plate_model.UnknownPlate]:
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
                    return unknown_plate_model.UnknownPlate(
                        id=row[0],
                        plate_number=row[1],
                        timestamp=row[2],
                        camera_id=row[3],
                        plates_photo_url=row[4],
                    )
        except Exception as e:
            self.conn.rollback()
            print(f"UnknownPlateRepository.create error: {e}")
        return None