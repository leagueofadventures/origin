import logging
import logging.handlers
import os
import json
from datetime import datetime
from typing import Dict, Any
import threading

# Определяем текущую директорию проекта
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

class AdvancedLogger:
    def __init__(self, log_dir: str = None):
        if log_dir is None:
            log_dir = os.path.join(PROJECT_DIR, 'Карта', 'logs')
        self.log_dir = log_dir
        os.makedirs(log_dir, exist_ok=True)

        # Создаем форматтеры
        self.detailed_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s:%(lineno)d - %(message)s'
        )
        self.simple_formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )

        # Настраиваем основной логгер
        self.logger = logging.getLogger('game_server')
        self.logger.setLevel(logging.DEBUG)

        # Обработчик файла с ротацией
        log_file = os.path.join(log_dir, f"server_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
        file_handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10*1024*1024, backupCount=5
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(self.detailed_formatter)

        # Консольный обработчик
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_handler.setFormatter(self.simple_formatter)

        # Добавляем обработчики
        self.logger.addHandler(file_handler)
        self.logger.addHandler(console_handler)

        # Локальное хранилище потока для контекста запроса
        self.local = threading.local()

    def log_connection(self, client_id: int, action: str, details: Dict[str, Any] = None):
        """Логировать события подключения"""
        message = f"Клиент {client_id}: {action}"
        if details:
            message += f" - {json.dumps(details)}"
        self.logger.info(message)

    def log_admin_action(self, client_id: int, action: str, details: Dict[str, Any] = None):
        """Логировать админские действия"""
        message = f"Админ {client_id}: {action}"
        if details:
            message += f" - {json.dumps(details)}"
        self.logger.info(message)

    def log_game_event(self, event_type: str, details: Dict[str, Any]):
        """Логировать игровые события"""
        message = f"Игровое событие: {event_type} - {json.dumps(details)}"
        self.logger.info(message)

    def log_error(self, error: Exception, context: str = ""):
        """Логировать ошибки с контекстом"""
        message = f"Ошибка в {context}: {str(error)}"
        self.logger.error(message, exc_info=True)

    def set_request_context(self, client_id: int, ip: str):
        """Установить контекст для текущего запроса"""
        self.local.client_id = client_id
        self.local.ip = ip

    def get_request_context(self) -> Dict[str, Any]:
        """Получить текущий контекст запроса"""
        return {
            'client_id': getattr(self.local, 'client_id', None),
            'ip': getattr(self.local, 'ip', None)
        }

# Глобальный экземпляр логгера
logger = AdvancedLogger()
