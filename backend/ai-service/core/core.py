from core.live_processor import LiveCameraProcessor

_live_processors: dict = {}


def process_camera(name, url):
    """Запускает обработку живого RTSP-потока."""
    processor = LiveCameraProcessor(video_source=url, name=name)
    processor.start_processing()
    _live_processors[name] = processor


def get_live_processor(name: str):
    return _live_processors.get(name)


def stop_camera(name: str):
    """Останавливает обработку потока камеры и удаляет её из реестра."""
    processor = _live_processors.pop(name, None)
    if processor:
        processor.stop_processing()