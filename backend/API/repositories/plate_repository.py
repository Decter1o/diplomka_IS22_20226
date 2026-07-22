from typing import Optional
from models.plate_model import Plate
from .db import DB


class PlateRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")

    def get_by_number(self, plate_number: str) -> Optional[Plate]:
        """Ищет номерной знак в базе. Возвращает Plate или None если не найден."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT plate_id, plate_number, driver_id
                    FROM plates
                    WHERE plate_number = %s
                    LIMIT 1
                    """,
                    (plate_number,)
                )
                row = cur.fetchone()
                if row:
                    return Plate(
                        plate_id=row[0],
                        plate_number=row[1],
                        driver_id=row[2],
                    )
        except Exception as e:
            print(f"PlateRepository.get_by_number error: {e}")
        return None

    def get_plate_with_driver(self, plate_number: str):
        """Ищет номер в базе и возвращает информацию о водителе."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.plate_id, p.plate_number, p.driver_id,
                           d.first_name, d.last_name, d.iin
                    FROM plates p
                    LEFT JOIN drivers d ON p.driver_id = d.driver_id
                    WHERE p.plate_number = %s
                    LIMIT 1
                    """,
                    (plate_number,)
                )
                row = cur.fetchone()
                if row:
                    return {
                        "plate_id": row[0],
                        "plate_number": row[1],
                        "driver_id": row[2],
                        "driver_name": f"{row[3]} {row[4]}" if row[3] else "N/A",
                        "iin": row[5]
                    }
        except Exception as e:
            print(f"PlateRepository.get_plate_with_driver error: {e}")
        return None