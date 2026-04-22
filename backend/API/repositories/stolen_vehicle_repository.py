from datetime import datetime
from typing import Optional
from uuid import UUID
from models.stolen_vehicle_model import StolenVehicle
from .db import DB


class StolenVehicleRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")

    def is_stolen(self, plate_number: str) -> bool:
        """Проверяет, числится ли номер в базе угнанных. Возвращает True/False."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM stolen_vehicles
                    WHERE plate_number = %s
                    LIMIT 1
                    """,
                    (plate_number,)
                )
                return cur.fetchone() is not None
        except Exception as e:
            print(f"StolenVehicleRepository.is_stolen error: {e}")
        return False

    def get_by_number(self, plate_number: str) -> Optional[StolenVehicle]:
        """Возвращает запись об угнанном авто по номеру или None."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, plate_number, reported_at, description
                    FROM stolen_vehicles
                    WHERE plate_number = %s
                    LIMIT 1
                    """,
                    (plate_number,)
                )
                row = cur.fetchone()
                if row:
                    return StolenVehicle(
                        id=row[0],
                        plate_number=row[1],
                        reported_at=row[2],
                        description=row[3],
                    )
        except Exception as e:
            print(f"StolenVehicleRepository.get_by_number error: {e}")
        return None

    def create(self, plate_number: str,
               description: Optional[str] = None) -> Optional[StolenVehicle]:
        """Добавляет авто в список угнанных. Возвращает созданную запись."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stolen_vehicles (plate_number, description)
                    VALUES (%s, %s)
                    RETURNING id, plate_number, reported_at, description
                    """,
                    (plate_number, description)
                )
                row = cur.fetchone()
                self.conn.commit()
                if row:
                    return StolenVehicle(
                        id=row[0],
                        plate_number=row[1],
                        reported_at=row[2],
                        description=row[3],
                    )
        except Exception as e:
            self.conn.rollback()
            print(f"StolenVehicleRepository.create error: {e}")
        return None

    def delete(self, plate_number: str) -> bool:
        """Удаляет авто из списка угнанных. Возвращает True при успехе."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM stolen_vehicles WHERE plate_number = %s",
                    (plate_number,)
                )
                self.conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            self.conn.rollback()
            print(f"StolenVehicleRepository.delete error: {e}")
        return False