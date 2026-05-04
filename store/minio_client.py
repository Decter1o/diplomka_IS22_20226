import io
import tomllib
import os
from minio import Minio
from minio.error import S3Error


def _load_config():
    config_path = os.path.join(os.path.dirname(__file__), 'minio_config.toml')
    with open(config_path, 'rb') as f:
        return tomllib.load(f)


class MinioStorage:
    """Клиент для загрузки фото номеров в MinIO.

    Загружает кроп номера и полный кадр напрямую из памяти,
    без записи временных файлов на диск.
    """

    def __init__(self, logger=None):
        config = _load_config()
        minio_cfg = config['minio']

        self.bucket = minio_cfg['BUCKET']
        self.endpoint = minio_cfg['ENDPOINT']
        self.logger = logger

        self._client = Minio(
            endpoint=minio_cfg['ENDPOINT'],
            access_key=minio_cfg['ACCESS_KEY'],
            secret_key=minio_cfg['SECRET_KEY'],
            secure=minio_cfg['SECURE'],
        )

        self._ensure_bucket()

    def _ensure_bucket(self):
        """Создаёт бакет если он ещё не существует."""
        try:
            if not self._client.bucket_exists(self.bucket):
                self._client.make_bucket(self.bucket)
                if self.logger:
                    self.logger.info(f"MinIO bucket '{self.bucket}' created")
        except S3Error as e:
            if self.logger:
                self.logger.error(f"MinIO bucket error: {e}")

    def upload_from_bytes(self, buf: bytes, object_name: str) -> str:
        """Загружает байты в MinIO и возвращает публичный URL объекта.

        Аргументы:
        - buf: байты файла (результат cv2.imencode)
        - object_name: имя объекта в бакете (например 'plate_cam1_42_1234.jpg')

        Возвращает URL вида http://minio:9000/plates/plate_cam1_42_1234.jpg
        """
        try:
            data = io.BytesIO(buf)
            self._client.put_object(
                bucket_name=self.bucket,
                object_name=object_name,
                data=data,
                length=len(buf),
                content_type='image/jpeg',
            )
            url = f"http://{self.endpoint}/{self.bucket}/{object_name}"
            if self.logger:
                self.logger.debug(f"MinIO uploaded: {url}")
            return url
        except S3Error as e:
            if self.logger:
                self.logger.error(f"MinIO upload error for '{object_name}': {e}")
            return ''

    def upload_plate_pair(self, crop_buf: bytes, full_buf: bytes,
                          camera_name: str, tid: int, ts: int) -> tuple[str, str]:
        """Загружает кроп номера и полный кадр, возвращает два URL.

        Аргументы:
        - crop_buf: байты кропа номера
        - full_buf: байты полного кадра
        - camera_name: имя камеры
        - tid: ID трека
        - ts: временная метка в миллисекундах

        Возвращает кортеж (crop_url, full_url).
        Если загрузка не удалась — возвращает пустые строки.
        """
        crop_name = f"plate_{camera_name}_{tid}_{ts}.jpg"
        full_name = f"plate_{camera_name}_{tid}_{ts}_full.jpg"

        crop_url = self.upload_from_bytes(crop_buf, crop_name)
        full_url = self.upload_from_bytes(full_buf, full_name)

        return crop_url, full_url
