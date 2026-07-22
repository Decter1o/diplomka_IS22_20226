import httpx
import logging
from uuid import UUID
from repositories.camera_repository import CameraRepository

logger = logging.getLogger(__name__)


class CameraService:
    """Сервис для управления камерами и синхронизации с MediaMTX."""

    def __init__(self):
        self.camera_repo = CameraRepository()
        self.mediamtx_url = "http://mediamtx:8080"

    async def create_camera(self, name: str, location: str, rtsp_url: str):
        """Создаёт новую камеру в БД и добавляет её в MediaMTX.

        Args:
            name: Имя камеры
            location: Локация камеры
            rtsp_url: RTSP URL источника

        Returns:
            Созданный объект Camera или None при ошибке

        Raises:
            Exception: При ошибке в БД или MediaMTX API
        """
        camera = self.camera_repo.create(
            name=name,
            location=location,
            rtsp_url=rtsp_url,
            status=True
        )

        if not camera:
            raise Exception("Failed to create camera in database")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.mediamtx_url}/v3/config/paths/add/{name}",
                    json={"source": rtsp_url},
                    timeout=5.0
                )
                if response.status_code not in [200, 201]:
                    self.camera_repo.delete(camera.camera_id)
                    raise Exception(f"MediaMTX error: {response.text}")
        except Exception as e:
            self.camera_repo.delete(camera.camera_id)
            logger.error(f"Failed to add camera to MediaMTX: {e}")
            raise

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"http://ai-service:8000/camera/{name}/start",
                    timeout=10.0
                )
        except Exception as e:
            logger.warning(f"Failed to notify ai-service to start camera '{name}': {e}")

        logger.info(f"Camera '{name}' created successfully")
        return camera

    async def delete_camera(self, camera_id: UUID):
        """Удаляет камеру из БД и из MediaMTX.

        Args:
            camera_id: UUID камеры для удаления

        Returns:
            True если успешно удалено, False иначе

        Raises:
            Exception: При ошибке в БД или MediaMTX API
        """
        camera = self.camera_repo.get_by_id(camera_id)

        if not camera:
            raise Exception("Camera not found")

        try:
            async with httpx.AsyncClient() as client:
                response = await client.delete(
                    f"{self.mediamtx_url}/v3/config/paths/remove/{camera.name}",
                    timeout=5.0
                )
                if response.status_code not in [200, 204]:
                    raise Exception(f"MediaMTX error: {response.text}")
        except Exception as e:
            logger.error(f"Failed to remove camera from MediaMTX: {e}")
            raise

        success = self.camera_repo.delete(camera_id)
        if not success:
            raise Exception("Failed to delete camera from database")

        try:
            async with httpx.AsyncClient() as client:
                await client.delete(
                    f"http://ai-service:8000/camera/{camera.name}/stop",
                    timeout=5.0
                )
        except Exception as e:
            logger.warning(f"Failed to notify ai-service to stop camera '{camera.name}': {e}")

        logger.info(f"Camera '{camera.name}' deleted successfully")
        return True

    async def sync_cameras_to_mediamtx(self):
        """Синхронизирует все камеры из БД с MediaMTX при старте.

        Загружает все камеры из БД и добавляет их в MediaMTX если они там отсутствуют.
        """
        cameras = self.camera_repo.get_all()

        for camera in cameras:
            if not camera.rtsp_url:
                logger.warning(f"Camera '{camera.name}' has no RTSP URL, skipping")
                continue

            try:
                async with httpx.AsyncClient() as client:
                    await client.post(
                        f"{self.mediamtx_url}/v3/config/paths/add/{camera.name}",
                        json={"source": camera.rtsp_url},
                        timeout=5.0
                    )
                logger.info(f"Synced camera '{camera.name}' to MediaMTX")
            except Exception as e:
                logger.warning(f"Failed to sync camera '{camera.name}' to MediaMTX: {e}")
