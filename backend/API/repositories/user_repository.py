from models import user_model
from .db import DB

class UserRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")

    def get_all_users(self):
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT uuid, username, password, role FROM users")
            rows = cursor.fetchall()
            if not rows:
                return ["No users found"]
            return [user_model.User(uuid=row[0], username=row[1], password=row[2], role=row[3]) for row in rows]