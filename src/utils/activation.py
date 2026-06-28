"""Модуль отслеживания и переключения состояний активации систем аимбота и триггера."""

import threading

from src.utils.config import config
from src.utils.mouse import is_button_pressed
from src.utils.mouse import is_key_pressed as backend_is_key_pressed

# Глобальное runtime-состояние активации основных функций
_activation_states = {
    "main": {
        "toggle_state": False,
        "use_enable_state": False,
        "last_button_state": False,
        "lock": threading.Lock(),
    },
    "sec": {
        "toggle_state": False,
        "use_enable_state": False,
        "last_button_state": False,
        "lock": threading.Lock(),
    },
}

# Состояние режима прицеливания (ADS) и триггера
_ads_states = {
    "main": {
        "toggle_state": False,
        "last_button_state": False,
        "lock": threading.Lock(),
    },
    "sec": {
        "toggle_state": False,
        "last_button_state": False,
        "lock": threading.Lock(),
    },
    "trigger": {
        "toggle_state": False,
        "last_button_state": False,
        "lock": threading.Lock(),
    },
}

# Карта соответствия названий кнопок их внутренним индексам
_BUTTON_NAME_TO_IDX = {
    "left mouse button": 0,
    "right mouse button": 1,
    "middle mouse button": 2,
    "side mouse 4 button": 3,
    "side mouse 5 button": 4,
}


def _normalize_button_idx(button_val):
    """Приводит переданный идентификатор или название кнопки к числовому индексу."""
    if isinstance(button_val, int):
        return button_val
    if isinstance(button_val, float):
        return int(button_val)
    val_str = str(button_val).strip().lower()
    if val_str.isdigit():
        return int(val_str)
    return _BUTTON_NAME_TO_IDX.get(val_str, button_val)


def is_binding_pressed(button_idx) -> bool:
    """Проверяет физическое нажатие кнопки мыши или клавиши клавиатуры.

    Args:
        button_idx: Индекс/название кнопки мыши или строковый токен клавиши.

    Returns:
        bool: True, если кнопка или клавиша нажата, иначе False.
    """
    if button_idx is None:
        return False
    norm = _normalize_button_idx(button_idx)
    if isinstance(norm, int) and 0 <= norm <= 4:
        return bool(is_button_pressed(norm))
    return bool(backend_is_key_pressed(str(button_idx)))


def check_ads_activation(button_idx, activation_type: str, mode_key: str = "main") -> bool:
    """Проверяет состояние режима прицеливания (ADS/Trigger) с учетом типа активации.

    Args:
        button_idx: Индекс или токен привязанной клавиши.
        activation_type: Режим работы ("hold_enable", "hold_disable", "toggle").
        mode_key: Идентификатор подсистемы ("main", "sec", "trigger").

    Returns:
        bool: Текущий статус активности режима.
    """
    current_pressed = bool(is_binding_pressed(button_idx))
    state = _ads_states.get(mode_key, _ads_states["main"])

    with state["lock"]:
        last_pressed = state["last_button_state"]

        if activation_type == "hold_enable":
            result = current_pressed
        elif activation_type == "hold_disable":
            result = not current_pressed
        elif activation_type == "toggle":
            if not last_pressed and current_pressed:
                state["toggle_state"] = not state["toggle_state"]
            result = state["toggle_state"]
        else:
            result = current_pressed

        state["last_button_state"] = current_pressed

    return result


def check_aim_activation(button_idx, activation_type: str, is_sec: bool = False) -> bool:
    """Проверяет и обновляет логическое состояние активации аимбота.

    Args:
        button_idx: Индекс кнопки или клавиатурный токен.
        activation_type: Алгоритм проверки ("hold_enable", "hold_disable", "toggle", "use_enable").
        is_sec: Флаг использования вторичного профиля настроек.

    Returns:
        bool: True, если функция должна работать в текущий момент.
    """
    current_pressed = bool(is_binding_pressed(button_idx))

    key = "sec" if is_sec else "main"
    state = _activation_states[key]

    with state["lock"]:
        last_pressed = state["last_button_state"]

        if activation_type == "hold_enable":
            result = current_pressed
        elif activation_type == "hold_disable":
            result = not current_pressed
        elif activation_type == "toggle":
            if not last_pressed and current_pressed:
                state["toggle_state"] = not state["toggle_state"]
            result = state["toggle_state"]
        elif activation_type == "use_enable":
            if not last_pressed and current_pressed:
                state["use_enable_state"] = not state["use_enable_state"]
            result = state["use_enable_state"]
        else:
            result = current_pressed

        state["last_button_state"] = current_pressed

    return result


def reset_activation_state(is_sec: bool = False) -> None:
    """Сбрасывает триггеры и сохраненные состояния runtime-активации аимбота.

    Args:
        is_sec: Флаг для сброса вторичного (True) или основного (False) профиля.
    """
    key = "sec" if is_sec else "main"
    state = _activation_states[key]
    with state["lock"]:
        state["toggle_state"] = False
        state["use_enable_state"] = False
        state["last_button_state"] = False


def reset_ads_state(mode_key: str = "main") -> None:
    """Очищает внутреннюю историю нажатий и переключений для режимов ADS/Trigger.

    Args:
        mode_key: Название сбрасываемой подсистемы ("main", "sec", "trigger").
    """
    state = _ads_states.get(mode_key, _ads_states["main"])
    with state["lock"]:
        state["toggle_state"] = False
        state["last_button_state"] = False

# Проксируем вызов старого имени на обновленное по PEP 8
check_aimbot_activation = check_aim_activation


def get_active_aim_fov(is_sec: bool = False) -> float:
    """Возвращает текущий радиус FOV из конфигурации.
    
    Необходим для совместимости импортов в aim_system.
    """
    if is_sec:
        return float(config.get("aim_fov_radius_sec", config.get("aim_fov_radius", 120)))
    return float(config.get("aim_fov_radius", 120))

check_aimbot_activation = check_aim_activation


def get_active_aim_fov(is_sec: bool = False) -> float:
    """Возвращает радиус FOV аимбота из конфигурации."""
    if is_sec:
        return float(config.get("aim_fov_radius_sec", config.get("aim_fov_radius", 120)))
    return float(config.get("aim_fov_radius", 120))


def get_active_trigger_fov() -> float:
    """Возвращает радиус FOV триггербота из конфигурации.
    
    Необходим для устранения ImportError в Triggerbot.py.
    """
    return float(config.get("trigger_radius", 12))