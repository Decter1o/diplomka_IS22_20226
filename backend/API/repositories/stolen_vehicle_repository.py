from typing import Optional, List
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
                    SELECT 1 FROM stolen_vehicles sv
                    JOIN plates p ON sv.plate_id = p.plate_id
                    WHERE p.plate_number = %s
                    LIMIT 1
                    """,
                    (plate_number,)
                )
                return cur.fetchone() is not None
        except Exception as e:
            print(f"StolenVehicleRepository.is_stolen error: {e}")
        return False

    def get_all(self) -> List[StolenVehicle]:
        """Возвращает все записи об угнанных авто."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT sv.id, sv.plate_id, sv.reported_at, sv.description
                    FROM stolen_vehicles sv
                    ORDER BY sv.reported_at DESC
                    """
                )
                return [self._row_to_stolen(row) for row in cur.fetchall()]
        except Exception as e:
            print(f"StolenVehicleRepository.get_all error: {e}")
        return []

    def get_enriched(self) -> list:
        """Возвращает угнанные авто с номером, водителем и ИИН."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT sv.id, sv.plate_id, sv.reported_at, sv.description,
                           p.plate_number,
                           CASE WHEN d.first_name IS NOT NULL
                                THEN d.first_name || ' ' || d.last_name
                                ELSE NULL END AS driver_name,
                           d.iin
                    FROM stolen_vehicles sv
                    JOIN plates p ON sv.plate_id = p.plate_id
                    LEFT JOIN drivers d ON p.driver_id = d.driver_id
                    ORDER BY sv.reported_at DESC
                    """
                )
                return [
                    {
                        'id': str(row[0]) if row[0] else None,
                        'plate_id': str(row[1]),
                        'reported_at': row[2].isoformat() if row[2] else None,
                        'description': row[3],
                        'plate_number': row[4],
                        'driver_name': row[5],
                        'iin': row[6],
                    }
                    for row in cur.fetchall()
                ]
        except Exception as e:
            print(f"StolenVehicleRepository.get_enriched error: {e}")
        return []

    def get_by_plate_id(self, plate_id: UUID) -> Optional[StolenVehicle]:
        """Возвращает запись об угнанном авто по plate_id или None."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, plate_id, reported_at, description
                    FROM stolen_vehicles
                    WHERE plate_id = %s
                    LIMIT 1
                    """,
                    (str(plate_id),)
                )
                row = cur.fetchone()
                if row:
                    return self._row_to_stolen(row)
        except Exception as e:
            print(f"StolenVehicleRepository.get_by_plate_id error: {e}")
        return None

    def create(self, plate_id: UUID,
               description: Optional[str] = None) -> Optional[StolenVehicle]:
        """Добавляет авто в список угнанных по plate_id. Возвращает созданную запись."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO stolen_vehicles (plate_id, description)
                    VALUES (%s, %s)
                    RETURNING id, plate_id, reported_at, description
                    """,
                    (str(plate_id), description)
                )
                row = cur.fetchone()
                self.conn.commit()
                if row:
                    return self._row_to_stolen(row)
        except Exception as e:
            self.conn.rollback()
            print(f"StolenVehicleRepository.create error: {e}")
        return None

    def delete(self, plate_id: UUID) -> bool:
        """Удаляет авто из списка угнанных по plate_id. Возвращает True при успехе."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM stolen_vehicles WHERE plate_id = %s",
                    (str(plate_id),)
                )
                self.conn.commit()
                return cur.rowcount > 0
        except Exception as e:
            self.conn.rollback()
            print(f"StolenVehicleRepository.delete error: {e}")
        return False

    @staticmethod
    def _row_to_stolen(row) -> StolenVehicle:
        return StolenVehicle(
            id=row[0],
            plate_id=row[1],
            reported_at=row[2],
            description=row[3],
        )
