import json
import asyncio
import threading
import tomllib
import os
import logging
from confluent_kafka import Consumer, KafkaError

from repositories.camera_repository import CameraRepository
from service.detection_service import DetectionService

logger = logging.getLogger(__name__)


def _load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'broker_config.toml')
    with open(config_path, 'rb') as f:
        return tomllib.load(f)


class PlateConsumer:
    """Kafka-консьюмер для обработки событий распознавания номерных знаков.

    Запускается как фоновый поток при старте FastAPI.
    Для каждого сообщения вызывает DetectionService.process_plate().
    """

    def __init__(self, detection_service: DetectionService, loop: asyncio.AbstractEventLoop):
        config = _load_config()
        broker_cfg = config['broker']

        self.topic = broker_cfg['TOPIC']
        self.detection_service = detection_service
        self.camera_repo = CameraRepository()

        # event loop главного потока FastAPI — нужен для запуска async из потока
        self.loop = loop

        self._consumer = Consumer({
            'bootstrap.servers': broker_cfg['BOOTSTRAP_SERVERS'],
            'group.id': broker_cfg['GROUP_ID'],
            'auto.offset.reset': broker_cfg['AUTO_OFFSET_RESET'],
            'enable.auto.commit': broker_cfg['ENABLE_AUTO_COMMIT'],
        })

        self._running = False
        self._thread = None

    def _handle(self, payload: dict):
        """Обогащает payload camera_id и передаёт в DetectionService."""
        camera_name = payload.get('camera', '')

        camera = self.camera_repo.get_by_name(camera_name)
        if not camera:
            logger.warning(f"Camera '{camera_name}' not found in DB, skipping")
            return

        payload['camera_id'] = camera.camera_id

        # Запускаем async-метод из синхронного потока через event loop FastAPI
        future = asyncio.run_coroutine_threadsafe(
            self.detection_service.process_plate(payload),
            self.loop
        )
        future.result(timeout=10)

    def _poll_loop(self):
        self._consumer.subscribe([self.topic])
        logger.info(f"PlateConsumer subscribed to '{self.topic}'")

        while self._running:
            msg = self._consumer.poll(timeout=1.0)

            if msg is None:
                continue

            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                logger.error(f"Kafka consumer error: {msg.error()}")
                continue

            try:
                payload = json.loads(msg.value().decode('utf-8'))
                self._handle(payload)
                self._consumer.commit(msg)
            except json.JSONDecodeError as e:
                logger.error(f"Bad JSON in Kafka message: {e}")
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                # не коммитим — сообщение будет перечитано после рестарта

        self._consumer.close()
        logger.info("PlateConsumer stopped")

    def start(self):
        """Запускает консьюмер в фоновом потоке-демоне."""
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Останавливает poll-loop и ждёт завершения потока."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=10)