"""Модуль-адаптер логирования.

Проксирует вызовы функций логирования из старой подсистемы CVM-colorBot
в глобальный кольцевой буфер сообщений приложения.
"""

from src.utils.logger import logger


def log_print(message: str) -> None:
    """Анализирует текст сообщения и записывает его в буфер с нужным уровнем.

    Args:
        message: Строка лога, пришедшая из модулей CVM.
    """
    text = str(message).strip()
    if not text:
        return
    level = "INFO"
    upper = text.upper()
    if "[ERROR]" in upper:
        level = "ERROR"
    elif "[WARN]" in upper:
        level = "WARN"
    elif "[OK]" in upper or "SUCCESS" in upper:
        level = "OK"
    logger.log(text, level)


def log_move(dx: int, dy: int, label: str = "") -> None:
    """Регистрирует относительное перемещение указателя мыши.

    Args:
        dx: Смещение по оси X.
        dy: Смещение по оси Y.
        label: Метка источника или события.
    """
    _ = (dx, dy, label)


def log_click(source: str = "") -> None:
    """Регистрирует событие одиночного клика мыши.

    Args:
        source: Метка компонента, вызвавшего клик.
    """
    _ = source


def log_press(source: str = "") -> None:
    """Регистрирует событие нажатия клавиши или кнопки.

    Args:
        source: Метка компонента, вызвавшего нажатие.
    """
    _ = source


def log_release(source: str = "") -> None:
    """Регистрирует событие отпускания клавиши или кнопки.

    Args:
        source: Метка компонента, вызвавшего отпускание.
    """
    _ = source