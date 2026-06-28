"""Модуль автоматического выстрела (Triggerbot Engine).

Анализирует положение обнаруженных целей относительно прицела (центра экрана),
обрабатывает задержки, подтверждения кадров, состояние активационных клавиш
и выполняет асинхронные серии кликов с имитацией контрстрейфов.
"""

import random
import threading
import time
from typing import Any, Dict, List, Optional

try:
    import cv2
except Exception:
    cv2 = None

from src.utils.activation import get_active_trigger_fov, is_binding_pressed
from src.utils.config import config
from src.utils.debug_logger import log_print
from .trigger_strafe_helper import (
    apply_manual_wait_gate,
    reset_strafe_runtime_state,
    run_with_auto_strafe,
)

# Глобальный потокобезопасный runtime-словарь состояния триггербота
_triggerbot_state: Dict[str, Any] = {
    "last_trigger_time": 0.0,
    "current_cooldown": 0.0,
    "enter_range_time": None,
    "random_delay": None,
    "burst_state": None,  # Варианты: None, "waiting", "bursting"
    "burst_thread": None,
    "confirm_count": 0,
    "activation_last_pressed": False,
    "activation_toggle_state": False,
    "active_trigger_type": "current",
    "deactivation_release_sent": False,
    "strafe_manual_neutral_since": None,
    "burst_lock": threading.Lock(),
}


def _safe_destroy_window(name: str) -> None:
    """Безопасно уничтожает отладочное окно OpenCV, если оно существует."""
    if cv2 is None:
        return
    try:
        cv2.destroyWindow(name)
    except Exception:
        pass


def _close_trigger_debug_windows() -> None:
    """Закрывает все графические оверлеи отладки зон ROI триггербота."""
    _safe_destroy_window("ROI")
    _safe_destroy_window("Mask")


def _is_configured_binding(value: Any) -> bool:
    """Проверяет, задана ли валидная клавиша активации в конфигурации."""
    if value is None:
        return False
    return bool(str(value).strip().lower() not in ("", "none", "0"))


def _execute_burst_sequence(
    controller: Any,
    count_min: int,
    count_max: int,
    hold_min: float,
    hold_max: float,
    interval_min: float,
    interval_max: float,
) -> None:
    """Фоновый рабочий поток симуляции очереди выстрелов с контрстрейфами.

    Args:
        controller: Синглтон-фасад управления вводом мыши.
        count_min: Минимальное количество выстрелов в очереди.
        count_max: Максимальное количество выстрелов в очереди.
        hold_min: Минимальное время удержания клика (мс).
        hold_max: Максимальное время удержания клика (мс).
        interval_min: Минимальная пауза между выстрелами (мс).
        interval_max: Максимальная пауза между выстрелами (мс).
    """
    try:
        shots = random.randint(int(count_min), max(int(count_min), int(count_max)))
        for i in range(shots):
            with _triggerbot_state["burst_lock"]:
                if _triggerbot_state["burst_state"] is None:
                    break

            def _perform_single_click() -> None:
                """Внутренний изолированный клик мыши с рандомизированным удержанием."""
                controller.left(1)
                h_time = random.uniform(float(hold_min), float(hold_max)) / 1000.0
                if h_time > 0:
                    time.sleep(h_time)
                controller.left(0)

            # Выполнение клика под защитой автоматического контрстрейфа
            run_with_auto_strafe(_perform_single_click)

            if i < shots - 1:
                p_time = random.uniform(float(interval_min), float(interval_max)) / 1000.0
                if p_time > 0:
                    time.sleep(p_time)
    except Exception as exc:
        log_print("[Triggerbot Burst Thread Error]", exc)
    finally:
        with _triggerbot_state["burst_lock"]:
            _triggerbot_state["burst_state"] = None
            _triggerbot_state["burst_thread"] = None


def process_triggerbot(
    targets: List[Any],
    frame_info: Any,
    img: Any,
    tracker_obj: Any,
    targets_trigger: Optional[List[Any]] = None,
) -> str:
    """Основной конвейер обработки логики триггербота (вызывается каждый кадр).

    Выполняет валидацию горячих клавиш, рассчитывает расстояние до прицела,
    проверяет кадры подтверждения, учитывает стрейф-мод и инициирует выстрелы.

    Args:
        targets: Список геометрических целей.
        frame_info: Метаданные текущего кадра (разрешение экрана).
        img: OpenCV матрица кадра.
        tracker_obj: Экземпляр родительского адаптера трекера.
        targets_trigger: Резервный список целей для триггербота.

    Returns:
        str: Текущий текстовый статус работы триггербота для GUI.
    """
    try:
        if targets_trigger is not None:
            use_targets = targets_trigger
        else:
            use_targets = targets

        controller = tracker_obj.controller

        # Проверка глобального включения триггербота в конфигурации
        if not getattr(config, "enabletrigger", False):
            with _triggerbot_state["burst_lock"]:
                if _triggerbot_state["burst_state"] is not None:
                    _triggerbot_state["burst_state"] = None
            _close_trigger_debug_windows()
            reset_strafe_runtime_state(_triggerbot_state)
            return "DISABLED"

        # Обработка логики удержания или переключения (Toggle) клавиш активации
        binding = getattr(config, "trigger_binding", None)
        if _is_configured_binding(binding):
            is_pressed = is_binding_pressed(binding)
            last_pressed = _triggerbot_state["activation_last_pressed"]
            _triggerbot_state["activation_last_pressed"] = is_pressed

            if getattr(config, "trigger_binding_mode", "Hold") == "Toggle":
                if is_pressed and not last_pressed:
                    _triggerbot_state["activation_toggle_state"] = (
                        not _triggerbot_state["activation_toggle_state"]
                    )
                active = _triggerbot_state["activation_toggle_state"]
            else:
                active = is_pressed
        else:
            active = True

        if not active:
            with _triggerbot_state["burst_lock"]:
                if _triggerbot_state["burst_state"] is not None:
                    _triggerbot_state["burst_state"] = None
            _close_trigger_debug_windows()
            reset_strafe_runtime_state(_triggerbot_state)
            return "HOLD_KEY"

        # Проверка нахождения в режиме активной стрельбы фонового потока
        with _triggerbot_state["burst_lock"]:
            if _triggerbot_state["burst_state"] == "bursting":
                return "BURST_IN_PROGRESS"

        now = time.time()
        last_t = _triggerbot_state["last_trigger_time"]
        cooldown = _triggerbot_state["current_cooldown"]

        if now - last_t < cooldown:
            reset_strafe_runtime_state(_triggerbot_state)
            return f"COOLDOWN ({cooldown - (now - last_t):.2f}s)"

        # Подтягивание динамических параметров рандомизации из конфига
        tb_fov = float(get_active_trigger_fov())
        tbconfirm_frames = int(getattr(config, "tbconfirm_frames", 0))
        tbdelay_min = float(getattr(config, "tbdelay_min", 0.0))
        tbdelay_max = float(getattr(config, "tbdelay_max", 0.0))

        tbburst_count_min = int(getattr(config, "tbburst_count_min", 1))
        tbburst_count_max = int(getattr(config, "tbburst_count_max", 1))
        tbhold_min = float(getattr(config, "tbhold_min", 20.0))
        tbhold_max = float(getattr(config, "tbhold_max", 40.0))
        tbburst_interval_min = float(getattr(config, "tbburst_interval_min", 10.0))
        tbburst_interval_max = float(getattr(config, "tbburst_interval_max", 30.0))
        tbcooldown_min = float(getattr(config, "tbcooldown_min", 0.1))
        tbcooldown_max = float(getattr(config, "tbcooldown_max", 0.3))

        # Поиск ближайшей к прицелу валидной цели
        target_in_fov = None
        if use_targets:
            best_target = min(use_targets, key=lambda t: t[2])
            if best_target[2] <= tb_fov:
                target_in_fov = best_target

        if target_in_fov is None:
            _triggerbot_state["enter_range_time"] = None
            _triggerbot_state["random_delay"] = None
            _triggerbot_state["confirm_count"] = 0
            reset_strafe_runtime_state(_triggerbot_state)
            return "SCANNING"

        # Фильтрация и валидация по счетчику кадров подтверждения цели
        if tbconfirm_frames > 0:
            _triggerbot_state["confirm_count"] += 1
            if _triggerbot_state["confirm_count"] < tbconfirm_frames:
                return f"CONFIRMING ({_triggerbot_state['confirm_count']}/{tbconfirm_frames})"

        # Расчет и фиксация начальной рандомизированной задержки реакции
        if _triggerbot_state["enter_range_time"] is None:
            _triggerbot_state["enter_range_time"] = now
            if tbdelay_max > tbdelay_min:
                _triggerbot_state["random_delay"] = (
                    random.uniform(tbdelay_min, tbdelay_max) / 1000.0
                )
            else:
                _triggerbot_state["random_delay"] = tbdelay_min / 1000.0

        enter_time = _triggerbot_state["enter_range_time"]
        random_delay = _triggerbot_state["random_delay"]
        elapsed = now - enter_time

        if elapsed >= random_delay:
            # Проверка шлюза ручного стрейфа (ожидание полной остановки)
            from .trigger_strafe_helper import get_strafe_mode, STRAFE_MODE_MANUAL_WAIT
            if get_strafe_mode() == STRAFE_MODE_MANUAL_WAIT:
                allowed, strafe_status = apply_manual_wait_gate(_triggerbot_state)
                if not allowed:
                    return strafe_status

            # Инициализация и запуск асинхронного потока симуляции стрельбы
            with _triggerbot_state["burst_lock"]:
                burst_thread = _triggerbot_state["burst_thread"]
                if (
                    burst_thread is not None 
                    and burst_thread.is_alive() 
                    and _triggerbot_state["burst_state"] == "bursting"
                ):
                    return "BURST_IN_PROGRESS"

                burst_thread = threading.Thread(
                    target=_execute_burst_sequence,
                    args=(
                        controller,
                        tbburst_count_min,
                        tbburst_count_max,
                        tbhold_min,
                        tbhold_max,
                        tbburst_interval_min,
                        tbburst_interval_max,
                    ),
                    daemon=True,
                )
                _triggerbot_state["burst_thread"] = burst_thread
                _triggerbot_state["burst_state"] = "bursting"
                _triggerbot_state["last_trigger_time"] = now
                _triggerbot_state["enter_range_time"] = None
                _triggerbot_state["random_delay"] = None
                _triggerbot_state["confirm_count"] = 0
                
                if float(tbcooldown_max) > 0:
                    _triggerbot_state["current_cooldown"] = random.uniform(
                        float(tbcooldown_min), float(tbcooldown_max)
                    )
                else:
                    _triggerbot_state["current_cooldown"] = 0.0

            burst_thread.start()
            return f"BURST_STARTED ({tbburst_count_min}-{tbburst_count_max} shots)"

        return f"WAITING ({elapsed:.3f}s/{random_delay:.3f}s)"
    except Exception as exc:
        log_print("[Triggerbot error]", exc)
        return f"ERROR: {str(exc)}"