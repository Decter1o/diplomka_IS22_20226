from models.user_model import UserRole
from .db import DB


class UserRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")

    def get_all_users(self):
        with self.conn.cursor() as cursor:
            cursor.execute(
                "SELECT uuid, username, role, is_active FROM users ORDER BY username"
            )
            rows = cursor.fetchall()
            return [
                {"uuid": str(r[0]), "username": r[1], "role": r[2], "is_active": r[3]}
                for r in rows
            ]

    def get_by_username(self, username: str):
        with self.conn.cursor() as cursor:
            cursor.execute(
                "SELECT uuid, username, hashed_password, role, is_active FROM users WHERE username = %s",
                (username,),
            )
            row = cursor.fetchone()
            if not row:
                return None
            return {
                "uuid": str(row[0]),
                "username": row[1],
                "hashed_password": row[2],
                "role": row[3],
                "is_active": row[4],
            }

    def create(self, username: str, password: str, role: UserRole = UserRole.operator):
        from auth.security import hash_password
        hashed = hash_password(password)
        with self.conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO users (username, hashed_password, role)
                VALUES (%s, %s, %s)
                RETURNING uuid, username, role, is_active
                """,
                (username, hashed, role.value),
            )
            row = cursor.fetchone()
            self.conn.commit()
            return {"uuid": str(row[0]), "username": row[1], "role": row[2], "is_active": row[3]}

    def delete(self, user_id: str) -> bool:
        with self.conn.cursor() as cursor:
            cursor.execute(
                "DELETE FROM users WHERE uuid = %s RETURNING uuid", (user_id,)
            )
            deleted = cursor.fetchone()
            self.conn.commit()
            return deleted is not None

    def migrate_plaintext_passwords(self):
        """На старте хэширует bcrypt-ом пароли, которые ещё хранятся открытым текстом."""
        from auth.security import hash_password
        with self.conn.cursor() as cursor:
            cursor.execute("SELECT uuid, hashed_password FROM users")
            rows = cursor.fetchall()
            for uid, pwd in rows:
                if pwd and not pwd.startswith("$2b$") and not pwd.startswith("$2a$"):
                    cursor.execute(
                        "UPDATE users SET hashed_password = %s WHERE uuid = %s",
                        (hash_password(pwd), uid),
                    )
            self.conn.commit()
