import os
import logging

class PlateLogger:
    _loggers = {}  # Кэш логгеров по имени

    @classmethod
    def get_logger(cls, name):
        if name not in cls._loggers:
            logger = logging.getLogger(f'PlateProcessor_{name}')
            logger.setLevel(logging.DEBUG)
            log_file = os.path.join(os.path.dirname(__file__), '..', f'{name}.log')
            handler = logging.FileHandler(log_file)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            cls._loggers[name] = logger
        return cls._loggers[name]