"""Mouse backend facade (CVM-colorBot).

Обеспечивает абстракцию над двумя режимами наводки:
  - SendInput - эмуляция мыши через Win32 API.
  - Serial    - отправка аппаратно-зависимых команд на контроллеры MAKCU/CH34x.
"""

from src.utils.debug_logger import log_print

from . import SendInputAPI, SerialAPI, state

BACKENDS = ("SendInput", "Serial")


def is_connected() -> bool:
    """Проверяет текущий статус подключения выбранного бэкенда.

    Returns:
        bool: True, если бэкенд инициализирован и подключен.
    """
    return bool(state.is_connected)


def _sync_public_state() -> None:
    """Внутренний метод синхронизации публичного состояния CVM API.

    Оставлен для обратной совместимости.
    """
    pass


def _normalize_api_name(mode: str) -> str:
    """Приводит строковое название API к эталонному названию бэкенда."""
    mode_norm = str(mode).strip().lower()
    if mode_norm in ("sendinput", "win32", "windows", "test"):
        return "SendInput"
    if mode_norm in ("serial", "makcu", "mak"):
        return "Serial"
    return "SendInput"


def _get_selected_backend_from_config() -> str:
    """Получает активный тип бэкенда мыши из конфигурации."""
    try:
        from src.utils.config import config
        return _normalize_api_name(getattr(config, "mouse_api", "SendInput"))
    except Exception:
        return "SendInput"


def _get_serial_settings(mode=None, port=None):
    """Извлекает настройки COM-порта и скорости передачи из конфигурации."""
    cfg_mode, cfg_port = "Auto", ""
    try:
        from src.utils.config import config
        cfg_mode = str(getattr(config, "serial_port", "Auto"))
        cfg_port = cfg_mode
    except Exception:
        pass

    if mode is not None:
        cfg_mode = str(mode)
    if port is not None:
        cfg_port = str(port)

    baud = 4000000
    try:
        from src.utils.config import config
        baud = int(getattr(config, "serial_baudrate", 4000000))
    except Exception:
        pass

    return cfg_mode, cfg_port, baud


def get_active_backend() -> str:
    """Возвращает строковый идентификатор активного в данный момент бэкенда.

    Returns:
        str: "SendInput" или "Serial".
    """
    return str(state.active_backend)


def get_last_connect_error() -> str:
    """Возвращает описание последней ошибки при попытке инициализации бэкенда.

    Returns:
        str: Текст ошибки или пустая строка.
    """
    return str(state.last_connect_error)


def disconnect_all() -> None:
    """Безопасно закрывает и сбрасывает все active подключения мыши."""
    state.set_connected(False)
    
    # Безопасное декоративное закрытие соединения
    if hasattr(SerialAPI, "close_serial"):
        try:
            SerialAPI.close_serial()
        except Exception:
            pass
    elif hasattr(SerialAPI, "close_port"):
        try:
            SerialAPI.close_port()
        except Exception:
            pass
    elif hasattr(state, "makcu") and state.makcu is not None:
        try:
            state.makcu.close()
            state.makcu = None
        except Exception:
            pass

    state.reset_button_states()


def connect_to_makcu(mode=None, port=None) -> bool:
    """Выполняет подключение к выбранному бэкенду управления курсором.

    Args:
        mode: Принудительный режим работы.
        port: Конкретный COM-порт для Serial бэкенда.

    Returns:
        bool: True в случае успешной инициализации бэкенда.
    """
    disconnect_all()
    backend = _get_selected_backend_from_config()
    state.active_backend = backend

    if backend == "SendInput":
        state.set_connected(True, "SendInput")
        log_print("[INFO] Mouse: активирован бэкенд SendInput (Win32 эмуляция)")
        return True

    if backend == "Serial":
        cfg_mode, cfg_port, baud = _get_serial_settings(mode, port)
        success = SerialAPI.open_serial(cfg_mode, baud)
        if success:
            log_print(f"[OK] Mouse: успешно подключено по Serial ({cfg_mode} @ {baud})")
            return True
        return False

    state.last_connect_error = f"Unknown backend: {backend}"
    return False


def switch_backend(backend_name: str) -> bool:
    """Переключает бэкенд мыши на лету во время работы приложения.

    Args:
        backend_name: Целевое имя бэкенда ("SendInput" или "Serial").

    Returns:
        bool: Результат операции переподключения.
    """
    try:
        from src.utils.config import config
        config.mouse_api = _normalize_api_name(backend_name)
    except Exception:
        pass
    return connect_to_makcu()


def switch_to_4m() -> bool:
    """Попытка сброса и переключения Serial соединения на максимальную скорость."""
    if not state.is_connected or state.active_backend != "Serial":
        return False
    return SerialAPI.switch_to_4m_command()


def is_button_pressed(button_idx: int) -> bool:
    """Проверяет логическое состояние нажатия кнопки мыши по её индексу.

    Args:
        button_idx: Внутренний индекс кнопки (0=LMB, 1=RMB, 2=MMB, 3=S4, 4=S5).

    Returns:
        bool: True, если кнопка зажата.
    """
    if not state.is_connected:
        return False
    idx = int(button_idx)
    if not (0 <= idx <= 4):
        return False

    if state.active_backend == "Serial":
        with state.button_states_lock:
            return bool(state.button_states[idx])

    return False


def is_key_pressed(key) -> bool:
    """Проверяет состояние клавиши клавиатуры (только для SendInput бэкенда).

    Args:
        key: Код или строковый токен клавиши.

    Returns:
        bool: True, если клавиша нажата.
    """
    if not state.is_connected:
        return False
    if state.active_backend == "SendInput":
        return bool(SendInputAPI.is_key_pressed_win32(key))
    return False


def move(x: float, y: float) -> None:
    """Выполняет относительное перемещение курсора мыши.

    Args:
        x: Смещение по оси X.
        y: Смещение по оси Y.
    """
    if not state.is_connected:
        return
    if state.active_backend == "SendInput":
        SendInputAPI.move(x, y)
    elif state.active_backend == "Serial":
        SerialAPI.move(x, y)


def left(is_down: int) -> None:
    """Управляет состоянием левой кнопки мыши (зажатие/отпускание).

    Args:
        is_down: 1 для нажатия, 0 для отпускания.
    """
    if not state.is_connected:
        return
    if state.active_backend == "SendInput":
        SendInputAPI.left(is_down)
    elif state.active_backend == "Serial":
        SerialAPI.left(is_down)


def test_move() -> None:
    """Выполняет тестовое круговое или диагональное движение для проверки связи."""
    if not state.is_connected:
        return
    if state.active_backend == "SendInput":
        SendInputAPI.move(10, 10)
        SendInputAPI.move(-10, -10)
    elif state.active_backend == "Serial":
        SerialAPI.move(20, 0)
        SerialAPI.move(-20, 0)


def tick_mouse_loops() -> None:
    """Тактовая функция для периодического обслуживания потоков блокировки ввода."""
    if state.is_connected and state.active_backend == "Serial":
        SerialAPI.tick_movement_lock_manager()

def tick_mouse_loops() -> None:
    """Тактовая функция для периодического обслуживания потоков блокировки ввода."""
    if state.is_connected and state.active_backend == "Serial":
        SerialAPI.tick_movement_lock_manager()


# ===========================================================================
# ДЕКОРАТИВНЫЙ АЛИАС ДЛЯ СОВМЕСТИМОСТИ С AIM_TRACKER / CVM API
# ===========================================================================
tick_movement_lock_manager = tick_mouse_loops


class Mouse:
    """Singleton-фасад мыши для совместимости с логикой наведения CVM-colorBot.

    Обеспечивает унифицированный интерфейс для команд перемещения и кликов.
    """

    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        """Инициализирует фасад мыши и проверяет автоподключение."""
        if hasattr(self, "_inited"):
            return
        auto_connect = False
        try:
            from src.utils.config import config
            auto_connect = bool(getattr(config, "auto_connect_mouse_api", False))
        except Exception:
            pass

        if auto_connect:
            if not connect_to_makcu():
                log_print(f"[ERROR] Mouse init failed: {get_last_connect_error()}")
        else:
            disconnect_all()
            log_print("[INFO] Mouse: ожидание ручного подключения из GUI.")
        self._inited = True

    def move(self, x: float, y: float) -> None:
        """Переместить курсор мыши."""
        move(x, y)

    def click(self) -> None:
        """Выполнить одиночный левый клик мыши."""
        if not state.is_connected:
            return
        left(1)
        left(0)

    def press(self) -> None:
        """Зажать левую кнопку мыши."""
        if state.is_connected:
            left(1)

    def release(self) -> None:
        """Отпустить левую кнопку мыши."""
        if state.is_connected:
            left(0)

    @staticmethod
    def is_pressed(button_idx: int) -> bool:
        """Проверить, зажата ли указанная кнопка."""
        return is_button_pressed(button_idx)


# ===========================================================================
# ДОБАВЛЕННЫЕ ФУНКЦИИ И ФЛАГИ ДЛЯ СОВМЕСТИМОСТИ С АИМ-СИСТЕМОЙ И СТРЕЙФАМИ
# ===========================================================================

# Алиас для aim_tracker.py (из позапрошлого сообщения)
tick_movement_lock_manager = tick_mouse_loops


# Функции для trigger_strafe_helper.py (из прошлого сообщения)
def key_down(key) -> None:
    """Зажимает клавишу клавиатуры через активный бэкенд мыши/ввода."""
    if not state.is_connected:
        return
    if state.active_backend == "SendInput":
        SendInputAPI.key_down(key)
    elif state.active_backend == "Serial":
        if hasattr(SerialAPI, "key_down"):
            SerialAPI.key_down(key)


def key_up(key) -> None:
    """Отпускает клавишу клавиатуры через активный бэкенд мыши/ввода."""
    if not state.is_connected:
        return
    if state.active_backend == "SendInput":
        SendInputAPI.key_up(key)
    elif state.active_backend == "Serial":
        if hasattr(SerialAPI, "key_up"):
            SerialAPI.key_up(key)


# Флаг совместимости интерфейса стрейфов для trigger_strafe_helper.py (новое)
supports_trigger_strafe_ui = True