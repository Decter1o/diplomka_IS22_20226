import json
import logging
from datetime import datetime
from typing import Optional, Set
from fastapi import WebSocket

from models.alert_model import AlertType
from repositories.detection_reposytory import DetectionRepository
from repositories.plate_repository import PlateRepository
from repositories.penalty_repository import PenaltyRepository
from repositories.unknow_plate_repository import UnknownPlateRepository
from repositories.alert_repository import AlertRepository
from repositories.stolen_vehicle_repository import StolenVehicleRepository

logger = logging.getLogger(__name__)


class DetectionService:
    """Сервис обработки событий распознавания номерных знаков.

    Оркестрирует полную цепочку обработки:
      - запись detection в БД
      - проверку номера на угон (приоритетно)
      - сверку номера с базой зарегистрированных
      - создание алерта при необходимости
      - уведомление клиентов по WebSocket
    """

    def __init__(self):
        self.detection_repo = DetectionRepository()
        self.plate_repo = PlateRepository()
        self.penalty_repo = PenaltyRepository()
        self.unknown_plate_repo = UnknownPlateRepository()
        self.alert_repo = AlertRepository()
        self.stolen_vehicle_repo = StolenVehicleRepository()

        # Активные WebSocket-соединения
        self._ws_clients: Set[WebSocket] = set()

    # ------------------------------------------------------------------
    # WebSocket-менеджер
    # ------------------------------------------------------------------

    def register_ws(self, ws: WebSocket):
        """Регистрирует новое WebSocket-соединение."""
        self._ws_clients.add(ws)

    def unregister_ws(self, ws: WebSocket):
        """Удаляет WebSocket-соединение."""
        self._ws_clients.discard(ws)

    async def _notify_websocket(self, payload: dict):
        """Отправляет JSON-уведомление всем подключённым клиентам.

        Если клиент отвалился — удаляет его из пула.
        """
        dead = set()
        for ws in self._ws_clients:
            try:
                await ws.send_text(json.dumps(payload, default=str))
            except Exception:
                dead.add(ws)
        self._ws_clients -= dead

    # ------------------------------------------------------------------
    # Основная логика
    # ------------------------------------------------------------------

    async def process_plate(self, payload: dict):
        """Главный метод. Вызывается из Kafka Consumer для каждого события.

        payload ожидает поля:
          camera           — имя камеры
          camera_id        — UUID камеры (передаётся consumer'ом после lookup)
          plate_number     — распознанный номер
          confidence       — уверенность OCR
          timestamp        — ISO 8601 строка
          plates_photo_url — URL фото кропа номера (опционально)
          full_photo_url   — URL полного кадра (опционально)
        """
        camera_id        = payload['camera_id']
        plate_number     = payload['plate_number']
        timestamp_str    = payload['timestamp']
        plates_photo_url = payload.get('plates_photo_url')
        full_photo_url   = payload.get('full_photo_url')
        camera_name      = payload.get('camera', '')

        try:
            detection_time = datetime.fromisoformat(timestamp_str)
        except ValueError:
            detection_time = datetime.now()

        # 1. Записываем detection
        detection = self.detection_repo.create(
            camera_id=camera_id,
            detection_time=detection_time,
            plates_photo_url=plates_photo_url,
            full_photo_url=full_photo_url,
        )
        if not detection:
            logger.error(f"Failed to create detection for plate={plate_number}")
            return

        # 2. Проверяем угон — приоритетная проверка, независимо от наличия в plates
        is_stolen = await self._check_stolen(
            plate_number=plate_number,
            detection=detection,
            camera_name=camera_name,
            plates_photo_url=plates_photo_url,
            full_photo_url=full_photo_url,
        )

        # 3. Ищем номер в базе зарегистрированных
        plate = self.plate_repo.get_by_number(plate_number)

        if not plate:
            # Номер не найден — сохраняем в unknown_plates (если не угнан — уведомляем отдельно)
            await self._handle_unknown(
                plate_number=plate_number,
                detection_time=detection_time,
                camera_id=camera_id,
                plates_photo_url=plates_photo_url,
                full_photo_url=full_photo_url,
                camera_name=camera_name,
                already_alerted=is_stolen,
            )
            return

        # 4. Номер найден — проверяем штрафы
        await self._check_penalties(
            plate=plate,
            detection=detection,
            camera_name=camera_name,
            plates_photo_url=plates_photo_url,
            full_photo_url=full_photo_url,
        )

    async def _check_stolen(self, plate_number: str, detection,
                             camera_name: str, plates_photo_url: Optional[str],
                             full_photo_url: Optional[str]) -> bool:
        """Проверяет, числится ли авто в угоне, и создаёт алерт если да.

        Возвращает True если алерт об угоне был создан.
        """
        if not self.stolen_vehicle_repo.is_stolen(plate_number):
            return False

        logger.warning(f"STOLEN vehicle detected: plate={plate_number}, camera={camera_name}")

        alert = self.alert_repo.create(
            driver_id=None,
            plate_id=None,
            detection_id=detection.detection_id,
            alert_type=AlertType.stolen,
        )

        if not alert:
            logger.error(f"Failed to create stolen alert for plate={plate_number}")
            return False

        await self._notify_websocket({
            "event": "alert",
            "alert_type": AlertType.stolen.value,
            "plate_number": plate_number,
            "camera": camera_name,
            "plates_photo_url": plates_photo_url,
            "full_photo_url": full_photo_url,
            "alert_id": str(alert.id),
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        })

        return True

    async def _handle_unknown(self, plate_number: str, detection_time: datetime,
                               camera_id, plates_photo_url: Optional[str],
                               full_photo_url: Optional[str], camera_name: str,
                               already_alerted: bool = False):
        """Сохраняет неизвестный номер и уведомляет клиентов.

        Если по этому номеру уже был создан алерт об угоне — WebSocket
        о unknown_plate не отправляем, чтобы не дублировать события.
        """
        self.unknown_plate_repo.create(
            plate_number=plate_number,
            timestamp=detection_time,
            camera_id=camera_id,
            plates_photo_url=plates_photo_url,
            full_photo_url=full_photo_url,
        )
        logger.info(f"Unknown plate saved: {plate_number}")

        if already_alerted:
            return

        await self._notify_websocket({
            "event": "unknown_plate",
            "plate_number": plate_number,
            "camera": camera_name,
            "timestamp": detection_time.isoformat(),
            "plates_photo_url": plates_photo_url,
            "full_photo_url": full_photo_url,
        })

    async def _check_penalties(self, plate, detection, camera_name: str,
                                plates_photo_url: Optional[str],
                                full_photo_url: Optional[str]):
        """Проверяет наличие неоплаченных штрафов и создаёт алерт если нужно."""
        has_debt = self.penalty_repo.has_unpaid(plate.driver_id)

        if not has_debt:
            logger.info(f"Plate {plate.plate_number}: no unpaid penalties, skipping alert")
            return

        alert = self.alert_repo.create(
            driver_id=plate.driver_id,
            plate_id=plate.plate_id,
            detection_id=detection.detection_id,
            alert_type=AlertType.wanted,
        )

        if not alert:
            logger.error(f"Failed to create alert for plate={plate.plate_number}")
            return

        logger.info(f"Alert created: plate={plate.plate_number}, driver={plate.driver_id}")

        await self._notify_websocket({
            "event": "alert",
            "alert_type": AlertType.wanted.value,
            "plate_number": plate.plate_number,
            "driver_id": str(plate.driver_id),
            "camera": camera_name,
            "plates_photo_url": plates_photo_url,
            "full_photo_url": full_photo_url,
            "alert_id": str(alert.id),
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        })