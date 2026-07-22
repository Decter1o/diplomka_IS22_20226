from typing import List, Optional
from uuid import UUID
from models import camera_model
from models.camera_model import Camera
from .db import DB


class CameraRepository(DB):
    def __init__(self):
        super().__init__()
        self.conn = self.get_connection()
        if self.conn is None:
            raise Exception("Failed to connect to the database")
    
    def get_by_name(self, name: str) -> Optional[Camera]:
        """Получает камеру по имени.

        Args:
            name: Имя камеры

        Returns:
            Camera объект или None если камера не найдена
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT camera_id, name, location, rtsp_url, status FROM cameras WHERE name = %s LIMIT 1",
                (name,)
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                return Camera(
                    camera_id=row[0],
                    name=row[1],
                    location=row[2],
                    rtsp_url=row[3],
                    status=row[4]
                )
            return None
        except Exception as e:
            print(f"Error getting camera by name '{name}': {e}")
            return None
    
    def get_by_id(self, camera_id: UUID) -> Optional[Camera]:
        """Получает камеру по UUID.

        Args:
            camera_id: UUID камеры

        Returns:
            Camera объект или None если камера не найдена
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT camera_id, name, location, rtsp_url, status FROM cameras WHERE camera_id = %s LIMIT 1",
                (str(camera_id),)
            )
            row = cursor.fetchone()
            cursor.close()

            if row:
                return Camera(
                    camera_id=row[0],
                    name=row[1],
                    location=row[2],
                    rtsp_url=row[3],
                    status=row[4]
                )
            return None
        except Exception as e:
            print(f"Error getting camera by id '{camera_id}': {e}")
            return None
    
    def get_all(self) -> List[Camera]:
        """Получает все камеры из базы данных.

        Returns:
            Список всех Camera объектов
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT camera_id, name, location, rtsp_url, status FROM cameras ORDER BY name")
            rows = cursor.fetchall()
            cursor.close()

            cameras = []
            for row in rows:
                cameras.append(Camera(
                    camera_id=row[0],
                    name=row[1],
                    location=row[2],
                    rtsp_url=row[3],
                    status=row[4]
                ))
            return cameras
        except Exception as e:
            print(f"Error getting all cameras: {e}")
            return []
    
    def create(self, name: str, location: str = "Unknown", status: bool = True, rtsp_url: str = None) -> Optional[Camera]:
        """Создает новую камеру в базе данных.

        Args:
            name: Имя камеры
            location: Локация камеры (по умолчанию "Unknown")
            status: Статус камеры (по умолчанию True)
            rtsp_url: RTSP URL камеры

        Returns:
            Созданный Camera объект или None если ошибка
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO cameras (name, location, rtsp_url, status) VALUES (%s, %s, %s, %s) RETURNING camera_id, name, location, rtsp_url, status",
                (name, location, rtsp_url, status)
            )
            row = cursor.fetchone()
            self.conn.commit()
            cursor.close()

            if row:
                return Camera(
                    camera_id=row[0],
                    name=row[1],
                    location=row[2],
                    rtsp_url=row[3],
                    status=row[4]
                )
            return None
        except Exception as e:
            self.conn.rollback()
            print(f"Error creating camera '{name}': {e}")
            return None
    
    def get_or_create_by_name(self, name: str, location: str = "Unknown") -> Optional[Camera]:
        """Получает камеру по имени или создает новую если не существует.

        Args:
            name: Имя камеры
            location: Локация камеры (используется при создании)

        Returns:
            Camera объект (либо существующий, либо вновь созданный)
        """
        camera = self.get_by_name(name)
        if camera is None:
            camera = self.create(name, location)
        return camera

    def delete(self, camera_id: UUID) -> bool:
        """Удаляет камеру по UUID.

        Args:
            camera_id: UUID камеры для удаления

        Returns:
            True если успешно удалено, False если ошибка или камера не найдена
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM cameras WHERE camera_id = %s", (str(camera_id),))
            self.conn.commit()
            success = cursor.rowcount > 0
            cursor.close()
            return success
        except Exception as e:
            self.conn.rollback()
            print(f"Error deleting camera '{camera_id}': {e}")
            return False

    def update(self, camera_id: UUID, name: str = None, location: str = None,
               rtsp_url: str = None, status: bool = None) -> Optional[Camera]:
        """Обновляет данные камеры.

        Args:
            camera_id: UUID камеры
            name: Новое имя (опционально)
            location: Новая локация (опционально)
            rtsp_url: Новый RTSP URL (опционально)
            status: Новый статус (опционально)

        Returns:
            Обновлённый Camera объект или None если ошибка
        """
        try:
            updates = []
            params = []

            if name is not None:
                updates.append("name = %s")
                params.append(name)
            if location is not None:
                updates.append("location = %s")
                params.append(location)
            if rtsp_url is not None:
                updates.append("rtsp_url = %s")
                params.append(rtsp_url)
            if status is not None:
                updates.append("status = %s")
                params.append(status)

            if not updates:
                return self.get_by_id(camera_id)

            params.append(str(camera_id))
            query = f"UPDATE cameras SET {', '.join(updates)} WHERE camera_id = %s"

            cursor = self.conn.cursor()
            cursor.execute(query, params)
            self.conn.commit()
            cursor.close()

            return self.get_by_id(camera_id)
        except Exception as e:
            self.conn.rollback()
            print(f"Error updating camera '{camera_id}': {e}")
            return None
