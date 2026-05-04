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
                "SELECT camera_id, name, location, status FROM cameras WHERE name = %s LIMIT 1",
                (name,)
            )
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                return Camera(
                    camera_id=row[0],
                    name=row[1],
                    location=row[2],
                    status=row[3]
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
                "SELECT camera_id, name, location, status FROM cameras WHERE camera_id = %s LIMIT 1",
                (str(camera_id),)
            )
            row = cursor.fetchone()
            cursor.close()
            
            if row:
                return Camera(
                    camera_id=row[0],
                    name=row[1],
                    location=row[2],
                    status=row[3]
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
            cursor.execute("SELECT camera_id, name, location, status FROM cameras ORDER BY name")
            rows = cursor.fetchall()
            cursor.close()
            
            cameras = []
            for row in rows:
                cameras.append(Camera(
                    camera_id=row[0],
                    name=row[1],
                    location=row[2],
                    status=row[3]
                ))
            return cameras
        except Exception as e:
            print(f"Error getting all cameras: {e}")
            return []
    
    def create(self, name: str, location: str = "Unknown", status: bool = True) -> Optional[Camera]:
        """Создает новую камеру в базе данных.
        
        Args:
            name: Имя камеры
            location: Локация камеры (по умолчанию "Unknown")
            status: Статус камеры (по умолчанию True)
            
        Returns:
            Созданный Camera объект или None если ошибка
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "INSERT INTO cameras (name, location, status) VALUES (%s, %s, %s) RETURNING camera_id, name, location, status",
                (name, location, status)
            )
            row = cursor.fetchone()
            self.conn.commit()
            cursor.close()
            
            if row:
                return Camera(
                    camera_id=row[0],
                    name=row[1],
                    location=row[2],
                    status=row[3]
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
        
        