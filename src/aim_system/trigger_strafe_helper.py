"""Модуль вспомогательной логики контрстрейфов (Triggerbot Strafe Helper).

Обеспечивает автоматическую остановку движения персонажа перед выстрелом триггербота
(эмуляция контрстрейфов) для достижения максимальной точности наведения.
"""

import ctypes
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.utils.config import config
from src.utils.mouse import is_key_pressed as backend_is_key_pressed
from src.utils.mouse import key_down, key_up, supports_trigger_strafe_ui
from src.utils.mouse.keycodes import to_vk_code

# Константы режимов работы стрейф-помощника
STRAFE_MODE_OFF: str = "off"
STRAFE_MODE_AUTO: str = "auto"
STRAFE_MODE_MANUAL_WAIT: str = "manual_wait"
_STRAFE_MODES: set = {STRAFE_MODE_OFF, STRAFE_MODE_AUTO, STRAFE_MODE_MANUAL_WAIT}

_MOVEMENT_KEYS: Tuple[str, ...] = ("W", "A", "S", "D")

try:
    _USER32 = ctypes.windll.user32
except Exception:
    _USER32 = None


def normalize_strafe_mode(value: Any) -> str:
    """Приводит переданное значение к валидному строковому режиму стрейфа.

    Args:
        value: Входное значение режима.

    Returns:
        str: Нормализованный токен режима ("off", "auto" или "manual_wait").
    """
    mode = str(value).strip().lower()
    if mode not in _STRAFE_MODES:
        return STRAFE_MODE_OFF
    return mode


def get_strafe_mode() -> str:
    """Возвращает текущий активный режим стрейфов из конфигурации приложения.

    Returns:
        str: Токен активного режима стрейфов.
    """
    if not supports_trigger_strafe_ui:
        return STRAFE_MODE_OFF
    return normalize_strafe_mode(getattr(config, "trigger_strafe_mode", STRAFE_MODE_OFF))


def reset_strafe_runtime_state(state_dict: Dict[str, Any]) -> None:
    """Сбрасывает runtime-таймеры состояния стрейфов во внутреннем словаре модуля.

    Args:
        state_dict: Словарь состояния триггербота.
    """
    state_dict["strafe_manual_neutral_since"] = None


def _read_local_hardware_key_pressed(key_str: str) -> bool:
    """Проверяет физическое нажатие клавиши в ОС через Win32 API.

    Args:
        key_str: Строковый символ клавиши ("W", "A", "S", "D").

    Returns:
        bool: True, если клавиша удерживается пользователем.
    """
    vk = to_vk_code(key_str)
    if vk is None or _USER32 is None:
        return False
    return bool(_USER32.GetAsyncKeyState(int(vk)) & 0x8000)


def _is_key_pressed_by_token(key_str: str) -> bool:
    """Универсально проверяет состояние клавиши через Win32 или активный бэкенд мыши.

    Args:
        key_str: Строковый токен клавиши.

    Returns:
        bool: Статус удержания клавиши.
    """
    try:
        if backend_is_key_pressed is not None:
            return bool(backend_is_key_pressed(key_str))
    except Exception:
        pass
    return _read_local_hardware_key_pressed(key_str)


def _sample_movement_snapshot() -> Dict[str, bool]:
    """Снимает карту текущих состояний нажатия для всех клавиш движения WASD.

    Returns:
        Dict[str, bool]: Словарь соответствия клавиш WASD их статусам нажатия.
    """
    return {k: _is_key_pressed_by_token(k) for k in _MOVEMENT_KEYS}


def check_manual_wait_neutral_strafe(state_dict: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Проверяет условия готовности выстрела в ручном режиме ожидания остановки.

    Персонаж должен полностью отпустить клавиши движения и переждать
    интервал стабилизации разброса.

    Args:
        state_dict: Внутренний runtime-словарь состояния триггербота.

    Returns:
        Tuple[bool, Optional[str]]: (Разрешение_на_выстрел, Строка_статуса_блокировки).
    """
    snapshot = _sample_movement_snapshot()
    any_moving = any(snapshot.values())

    if any_moving:
        state_dict["strafe_manual_neutral_since"] = None
        return False, "STRAFE_WAIT_MANUAL_NEUTRAL"

    neutral_since = state_dict.get("strafe_manual_neutral_since")
    if neutral_since is None:
        state_dict["strafe_manual_neutral_since"] = time.time()
        return False, "STRAFE_SET_NEUTRAL_ANCHOR"

    now = time.time()
    required_ms = float(getattr(config, "trigger_strafe_manual_wait_ms", 60.0))
    elapsed_ms = int((now - float(neutral_since)) * 1000.0)

    if elapsed_ms >= required_ms:
        return True, None
    return False, f"STRAFE_WAIT_NEUTRAL ({elapsed_ms}/{required_ms}ms)"


def _resolve_auto_opposing_keys() -> List[str]:
    """Вычисляет список клавиш контр-импульса на основе зажатых в данный момент.

    Если зажата 'A', для остановки нужно прожать 'D'. Если 'W' — то 'S'.

    Returns:
        List[str]: Список строковых токенов клавиш для автоматического прожима.
    """
    snapshot = _sample_movement_snapshot()
    result: List[str] = []

    a_pressed = bool(snapshot.get("A", False))
    d_pressed = bool(snapshot.get("D", False))
    if a_pressed and not d_pressed:
        result.append("D")
    elif d_pressed and not a_pressed:
        result.append("A")

    w_pressed = bool(snapshot.get("W", False))
    s_pressed = bool(snapshot.get("S", False))
    if w_pressed and not s_pressed:
        result.append("S")
    elif s_pressed and not w_pressed:
        result.append("W")

    return result


def _safe_key_down(key: str) -> None:
    """Безопасно имитирует нажатие клавиши с перехватом исключений."""
    try:
        key_down(key)
    except Exception:
        pass


def _safe_key_up(key: str) -> None:
    """Безопасно имитирует отпускание клавиши с перехватом исключений."""
    try:
        key_up(key)
    except Exception:
        pass


def run_with_auto_strafe(shot_func: Callable[[], Any]) -> Any:
    """Обертка-декоратор для выполнения выстрела с автоматическим контрстрейфом.

    Если активен авто-режим, метод высвобождает WASD, посылает компенсирующий
    импульс противоположными клавишами, выдерживает микро-паузу для фиксации модели,
    производит выстрел через shot_func и возвращает клавиши в исходное состояние.

    Args:
        shot_func: Функция (колбэк), совершающая фактический клик выстрела.

    Returns:
        Результат выполнения shot_func() или None.
    """
    mode = get_strafe_mode()
    if mode != STRAFE_MODE_AUTO:
        return shot_func()

    opposing_keys = _resolve_auto_opposing_keys()
    if not opposing_keys:
        return shot_func()

    snapshot = _sample_movement_snapshot()
    active_pressed = [k for k, pressed in snapshot.items() if pressed]

    # Шаг 1: Снимаем зажатие с текущих клавиш хода
    for k in active_pressed:
        _safe_key_up(k)

    # Шаг 2: Прожимаем противоположные клавиши контр-стрейфа
    for k in opposing_keys:
        _safe_key_down(k)

    # Шаг 3: Микро-пауза деселерации модели персонажа
    duration_ms = float(getattr(config, "trigger_strafe_auto_duration_ms", 45.0))
    if duration_ms > 0:
        time.sleep(duration_ms / 1000.0)

    # Шаг 4: Высвобождаем контр-клавиши
    for k in opposing_keys:
        _safe_key_up(k)

    # Шаг 5: Исполняем выстрел триггербота по зафиксированной цели
    res = shot_func()

    # Шаг 6: Возвращаем зажатие оригинальных клавиш для продолжения движения
    for k in active_pressed:
        _safe_key_down(k)

    return res

# ===========================================================================
# ОБЁРТКИ СОВМЕСТИМОСТИ ДЛЯ ИМПОРТОВ В TRIGGERBOT.PY
# ===========================================================================

def apply_manual_wait_gate(state_dict: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """Алиас-обёртка для совместимости с конвейером импортов Triggerbot.py.

    Перенаправляет вызов проверки состояния ручного стрейфа в базовую функцию.

    Args:
        state_dict: Внутренний runtime-словарь состояния триггербота.

    Returns:
        Tuple[bool, Optional[str]]: Результат проверки готовности ручного стрейфа.
    """
    return check_manual_wait_neutral_strafe(state_dict)