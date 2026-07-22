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
               camera_id: Optional[UUID] = None, job_id: Optional[UUID] = None,
               plates_photo_url: Optional[str] = None,
               full_photo_url: Optional[str] = None
               ) -> Optional[unknow_plate_model.UnknownPlate]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO unknown_plates
                        (plate_number, timestamp, camera_id, job_id, plates_photo_url, full_photo_url, status)
                    VALUES (%s, %s, %s, %s, %s, %s, 'unrecognized')
                    RETURNING id, plate_number, timestamp, camera_id, job_id,
                              plates_photo_url, full_photo_url, status, corrected_plate_number
                    """,
                    (plate_number, timestamp,
                     str(camera_id) if camera_id else None,
                     str(job_id) if job_id else None,
                     plates_photo_url, full_photo_url)
                )
                row = cur.fetchone()
                self.conn.commit()
                if row:
                    return self._row_to_unknown(row)
        except Exception as e:
            self.conn.rollback()
            print(f"UnknownPlateRepository.create error: {e}")
        return None

    def get_all(self, limit: int = 100, offset: int = 0,
                camera_id: Optional[UUID] = None, status: Optional[str] = None,
                start_date: Optional[datetime] = None, end_date: Optional[datetime] = None
                ) -> List[unknow_plate_model.UnknownPlate]:
        """Возвращает список неизвестных номеров, свежие первыми."""
        try:
            with self.conn.cursor() as cur:
                query = "SELECT id, plate_number, timestamp, camera_id, job_id, plates_photo_url, full_photo_url, status, corrected_plate_number FROM unknown_plates WHERE 1=1"
                params = []

                if camera_id:
                    query += " AND camera_id = %s"
                    params.append(str(camera_id))
                if status:
                    query += " AND status = %s"
                    params.append(status)
                if start_date:
                    query += " AND timestamp >= %s"
                    params.append(start_date)
                if end_date:
                    query += " AND timestamp <= %s"
                    params.append(end_date)

                query += " ORDER BY timestamp DESC LIMIT %s OFFSET %s"
                params.extend([limit, offset])

                cur.execute(query, params)
                return [self._row_to_unknown(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"UnknownPlateRepository.get_all error: {e}")
        return []

    def update(self, unknown_plate_id: UUID, corrected_plate_number: str, status: str) -> bool:
        """Обновить статус и введённый номер."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE unknown_plates
                    SET corrected_plate_number = %s, status = %s
                    WHERE id = %s
                    """,
                    (corrected_plate_number, status, str(unknown_plate_id))
                )
                self.conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            self.conn.rollback()
            print(f"UnknownPlateRepository.update error: {e}")
        return False

    @staticmethod
    def _row_to_unknown(row) -> unknow_plate_model.UnknownPlate:
        return unknow_plate_model.UnknownPlate(
            id=row[0],
            plate_number=row[1],
            timestamp=row[2],
            camera_id=row[3],
            job_id=row[4],
            plates_photo_url=row[5],
            full_photo_url=row[6],
            status=row[7],
            corrected_plate_number=row[8],
        )