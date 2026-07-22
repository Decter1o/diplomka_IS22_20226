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

    def create(self, source_type: str, detection_time: datetime,
               camera_id: Optional[UUID] = None,
               job_id: Optional[UUID] = None,
               plate_number: Optional[str] = None,
               plates_photo_url: Optional[str] = None,
               full_photo_url: Optional[str] = None) -> Optional[detection_model.Detection]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO detections
                        (source_type, camera_id, job_id, detection_time, plate_number, plates_photo_url, full_photo_url)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING detection_id, source_type, camera_id, job_id,
                              detection_time, plate_number, plates_photo_url, full_photo_url
                    """,
                    (
                        source_type,
                        str(camera_id) if camera_id else None,
                        str(job_id) if job_id else None,
                        detection_time, plate_number, plates_photo_url, full_photo_url,
                    )
                )
                row = cur.fetchone()
                self.conn.commit()
                if row:
                    return detection_model.Detection(
                        detection_id=row[0],
                        source_type=row[1],
                        camera_id=row[2],
                        job_id=row[3],
                        camera_name=None,
                        detection_time=row[4],
                        plate_number=row[5],
                        plates_photo_url=row[6],
                        full_photo_url=row[7],
                    )
        except Exception as e:
            self.conn.rollback()
            print(f"DetectionRepository.create error: {e}")
        return None

    def get_all(self, limit: int = 100, offset: int = 0,
                camera_id: Optional[UUID] = None,
                job_id: Optional[UUID] = None) -> List[detection_model.Detection]:
        try:
            with self.conn.cursor() as cur:
                conditions = []
                params = []

                if camera_id:
                    conditions.append("d.camera_id = %s")
                    params.append(str(camera_id))

                if job_id:
                    conditions.append("d.job_id = %s")
                    params.append(str(job_id))

                where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
                params += [limit, offset]

                cur.execute(
                    f"""
                    SELECT d.detection_id, d.source_type, d.camera_id, d.job_id,
                           c.name, d.detection_time, d.plate_number,
                           d.plates_photo_url, d.full_photo_url
                    FROM detections d
                    LEFT JOIN cameras c ON c.camera_id = d.camera_id
                    {where}
                    ORDER BY d.detection_time DESC
                    LIMIT %s OFFSET %s
                    """,
                    params
                )
                return [self._row_to_detection(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"DetectionRepository.get_all error: {e}")
        return []

    @staticmethod
    def _row_to_detection(row) -> detection_model.Detection:
        return detection_model.Detection(
            detection_id=row[0],
            source_type=row[1],
            camera_id=row[2],
            job_id=row[3],
            camera_name=row[4],
            detection_time=row[5],
            plate_number=row[6],
            plates_photo_url=row[7],
            full_photo_url=row[8],
        )