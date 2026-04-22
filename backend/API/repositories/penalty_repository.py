from typing import Optional
from uuid import UUID
from models.penalty_model import Penalty
from .db import DB


class PenaltyRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")

    def has_unpaid(self, driver_id: UUID) -> bool:
        """Проверяет наличие неоплаченных штрафов у водителя."""
        try:
            with self.conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1 FROM penalty
                    WHERE driver_id = %s AND payment_status = false
                    LIMIT 1
                    """,
                    (str(driver_id),)
                )
                return cur.fetchone() is not None
        except Exception as e:
            print(f"PenaltyRepository.has_unpaid error: {e}")
        return False