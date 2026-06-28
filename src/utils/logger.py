"""Модуль логирования.

Предоставляет потокобезопасный кольцевой буфер строк для регистрации
событий приложения и вывода логов в GUI.
"""

import threading
import time
from collections import deque


class DebugLogger:
    """Потокобезопасный кольцевой буфер лог-сообщений.

    Attributes:
        max_lines (int): Максимальное количество одновременно хранящихся строк.
    """

    def __init__(self, max_lines: int = 200) -> None:
        """Инициализирует кольцевой буфер и примитивы синхронизации.

        Args:
            max_lines: Максимальное количество хранимых строк лога.
        """
        self.max_lines = max_lines
        self._buf: deque = deque(maxlen=max_lines)
        self._lock = threading.Lock()

    def log(self, message: str, level: str = "INFO") -> None:
        """Форматирует сообщение и безопасно добавляет его в буфер лога.

        Args:
            message: Текст лог-сообщения.
            level: Уровень критичности (например, INFO, WARN, ERROR, OK).
        """
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] [{level}] {message}"
        with self._lock:
            self._buf.append((level, entry))

    def get_lines(self) -> list:
        """Возвращает снапшот всех текущих строк буфера.

        Returns:
            list: Список кортежей вида (level, entry).
        """
        with self._lock:
            return list(self._buf)

    def clear(self) -> None:
        """Полностью очищает внутренний буфер лог-сообщений."""
        with self._lock:
            self._buf.clear()


# Глобальный единственный экземпляр регистратора логов
logger = DebugLogger()