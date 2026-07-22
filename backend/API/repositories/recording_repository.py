from datetime import datetime
from typing import List, Optional

from .db import DB


class RecordingRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")

    def create(
        self,
        camera_path: str,
        minio_object: str,
        minio_url: str,
        started_at: Optional[datetime],
        ended_at: Optional[datetime],
        duration_sec: Optional[int],
        file_size: Optional[int],
    ) -> Optional[dict]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO recordings
                        (camera_path, minio_object, minio_url,
                         started_at, ended_at, duration_sec, file_size)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, camera_path, minio_object, minio_url,
                              started_at, ended_at, duration_sec, file_size, created_at
                    """,
                    (camera_path, minio_object, minio_url,
                     started_at, ended_at, duration_sec, file_size),
                )
                row = cur.fetchone()
                self.conn.commit()
                return self._to_dict(row) if row else None
        except Exception as e:
            self.conn.rollback()
            print(f"RecordingRepository.create error: {e}")
        return None

    def get_all(
        self,
        camera: Optional[str] = None,
        limit: int = 200,
        offset: int = 0,
    ) -> List[dict]:
        try:
            with self.conn.cursor() as cur:
                if camera:
                    cur.execute(
                        """
                        SELECT id, camera_path, minio_object, minio_url,
                               started_at, ended_at, duration_sec, file_size, created_at
                        FROM recordings
                        WHERE camera_path = %s
                        ORDER BY started_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (camera, limit, offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, camera_path, minio_object, minio_url,
                               started_at, ended_at, duration_sec, file_size, created_at
                        FROM recordings
                        ORDER BY started_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (limit, offset),
                    )
                return [self._to_dict(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"RecordingRepository.get_all error: {e}")
        return []

    def get_for_range(
        self, camera: str, start_dt: datetime, end_dt: datetime
    ) -> List[dict]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, camera_path, minio_object, minio_url,
                           started_at, ended_at, duration_sec, file_size, created_at
                    FROM recordings
                    WHERE camera_path = %s
                      AND started_at < %s
                      AND (ended_at > %s OR ended_at IS NULL)
                    ORDER BY started_at ASC
                    """,
                    (camera, end_dt, start_dt),
                )
                return [self._to_dict(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"RecordingRepository.get_for_range error: {e}")
        return []

    def get_cameras(self) -> List[str]:
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "SELECT DISTINCT camera_path FROM recordings ORDER BY camera_path"
                )
                return [row[0] for row in cur.fetchall()]
        except Exception as e:
            print(f"RecordingRepository.get_cameras error: {e}")
        return []

    @staticmethod
    def _to_dict(row) -> dict:
        return {
            "id": str(row[0]),
            "camera_path": row[1],
            "minio_object": row[2],
            "minio_url": row[3],
            "started_at": row[4].isoformat() if row[4] else None,
            "ended_at": row[5].isoformat() if row[5] else None,
            "duration_sec": row[6],
            "file_size": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
        }
