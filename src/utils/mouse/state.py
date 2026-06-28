"""Модуль глобального состояния подсистемы ввода (Mouse/Keyboard State).

Хранит общие runtime-переменные, структуры дескрипторов устройств и примитивы
синхронизации (блокировки) для обеспечения потокобезопасного взаимодействия
между GUI, CVM аимботом и аппаратными контроллерами.
"""

import threading
from typing import Any, Dict, Optional

# Глобальные дескрипторы подключений и потоков (CVM-colorBot)
makcu: Optional[Any] = None
makcu_lock: threading.Lock = threading.Lock()

# Потокобезопасный маппинг логических состояний кнопок мыши (0=LMB, 1=RMB, и т.д.)
button_states: Dict[int, bool] = {i: False for i in range(5)}
button_states_lock: threading.Lock = threading.Lock()

# Общий статус инициализации активного бэкенда
is_connected: bool = False
active_backend: str = "Serial"
last_connect_error: str = ""

# Ссылки на динамически загружаемые модули сторонних API (kmnet, kmbox, dhz)
kmnet_module: Optional[Any] = None
kmboxa_module: Optional[Any] = None
makv2_module: Optional[Any] = None
dhz_client: Optional[Any] = None

last_button_mask: int = 0
listener_thread: Optional[threading.Thread] = None
mask_applied_idx: Optional[int] = None

# Структура синхронизации блокировок наведения (Movement Lock Manager)
movement_lock_state: Dict[str, Any] = {
    "lock_x": False,
    "lock_y": False,
    "main_aimbot_locked": False,
    "sec_aimbot_locked": False,
    "last_main_move_time": 0.0,
    "last_sec_move_time": 0.0,
    "lock": threading.Lock(),
}


def set_connected(connected: bool, backend: Optional[str] = None) -> None:
    """Устанавливает статус подключения и обновляет имя активного бэкенда.

    Args:
        connected: Флаг успешности инициализации бэкенда.
        backend: Опциональное имя установленного бэкенда ("SendInput" / "Serial").
    """
    global is_connected, active_backend
    is_connected = bool(connected)
    if backend is not None:
        active_backend = str(backend)


def reset_button_states() -> None:
    """Потокобезопасно сбрасывает логическое состояние нажатия всех кнопок мыши."""
    global last_button_mask
    with button_states_lock:
        for i in range(5):
            button_states[i] = False
    last_button_mask = 0