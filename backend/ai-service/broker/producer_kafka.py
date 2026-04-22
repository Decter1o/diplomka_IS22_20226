import json
import os
import tomllib
from confluent_kafka import Producer


def _load_config():
    """Загружает конфигурацию из broker_config.toml."""
    config_path = os.path.join(os.path.dirname(__file__), 'broker_config.toml')
    with open(config_path, 'rb') as f:
        return tomllib.load(f)


class KafkaManager:
    """Менеджер для публикации событий обнаружения номеров в Kafka.
    
    Отправляет сообщения с данными о распознанных номеров в топик plate_detections.
    Используется AI Service для передачи результатов обработки в API Service.
    """

    def __init__(self, logger=None):
        """
        Инициализирует Kafka Producer.
        
        Args:
            logger: Логгер для логирования событий. Если None, логирование отключено.
        """
        config = _load_config()
        broker_cfg = config['broker']
        
        self.topic = broker_cfg['TOPIC']
        self.logger = logger
        
        self._producer = Producer({
            'bootstrap.servers': broker_cfg['BOOTSTRAP_SERVERS'],
            'client.id': 'ai-service-producer',
        })
    
    def _delivery_report(self, err, msg):
        """Callback для отчёта о доставке сообщения.
        
        Вызывается после попытки отправки сообщения в Kafka.
        Логирует успех или ошибку доставки.
        """
        if err is not None:
            if self.logger:
                self.logger.error(f"Message delivery failed: {err}")
        else:
            if self.logger:
                self.logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")
    
    def publish_detection(self, camera_name: str, plate_number: str,
                         confidence: float, timestamp: str,
                         plates_photo_url: str = '', full_photo_url: str = ''):
        """
        Публикует событие обнаружения номера в Kafka.
        
        Отправляет JSON сообщение в топик plate_detections с информацией о
        распознанном номере автомобиля, камере и уверенности распознавания.
        
        Args:
            camera_name: Имя камеры/источника видео.
            plate_number: Распознанный номер автомобиля.
            confidence: Уверенность OCR (0.0-1.0).
            timestamp: Временная метка события (ISO 8601 формат).
            plates_photo_url: URL или путь к изображению номера (опционально).
        
        Raises:
            Exception: Если возникла ошибка при отправке сообщения.
        """
        try:
            payload = {
                'camera': camera_name,
                'plate_number': plate_number,
                'confidence': confidence,
                'timestamp': timestamp,
                'plates_photo_url': plates_photo_url,
                'full_photo_url': full_photo_url,
            }
            
            message = json.dumps(payload)
            self._producer.produce(
                self.topic,
                value=message.encode('utf-8'),
                callback=self._delivery_report
            )
            
            # Убедиться, что сообщение отправлено в течение 5 секунд
            self._producer.flush(timeout=5)
            
            if self.logger:
                self.logger.info(
                    f"Published detection: plate={plate_number}, "
                    f"camera={camera_name}, confidence={confidence:.3f}"
                )
        except Exception as e:
            if self.logger:
                self.logger.error(f"Error publishing detection: {e}")
            raise
    
    def close(self):
        """Закрывает соединение с Kafka и гарантирует доставку всех сообщений.
        
        Должен быть вызван перед завершением AI Service для безопасного
        отключения и убеждения в том, что все сообщения были доставлены.
        """
        if self._producer:
            self._producer.flush()
            if self.logger:
                self.logger.info("KafkaManager closed")