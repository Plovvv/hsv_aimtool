"""Модуль системы контроля отдачи (Recoil Control System, RCS).

Обеспечивает автоматическое смещение курсора вниз (Pull-down) по оси Y при
удержании левой кнопки мыши для компенсации вертикальной отдачи оружия,
а также управляет временными интервалами разблокировки осей наведения.
"""

import threading
import time
from typing import Any, Dict, Optional

from src.utils.config import config
from src.utils.debug_logger import log_print
from src.utils.mouse import is_button_pressed

# Глобальный потокобезопасный runtime-словарь состояния RCS
_rcs_state: Dict[str, Any] = {
    "is_active": False,  # Флаг активности процесса компенсации
    "last_click_time": 0.0,  # Время последнего клика (для фильтрации быстрых нажатий)
    "button_press_time": None,  # Метка времени зажатия кнопки (для детекции Long Press)
    "rcs_thread": None,  # Ссылка на фоновый поток пулл-дауна
    "rcs_lock": threading.Lock()  # Примитив синхронизации потоков
}

# Менеджер состояния временной разблокировки оси Y
_y_release_state: Dict[str, Any] = {
    "is_released": False,  # Флаг текущего снятия блокировки с оси Y
    "release_start_time": None,  # Время начала интервала разблокировки
    "release_duration": 0.0,  # Рассчитанная длительность разблокировки (сек)
    "release_lock": threading.Lock()  # Примитив синхронизации потоков
}


def _rcs_pull_loop(controller: Any, pull_speed: float) -> None:
    """Внутренний циклический поток компенсации (Pull-down) отдачи.

    Непрерывно отправляет команды относительного смещения мыши вниз по оси Y
    с фиксированными микроинтервалами, пока удерживается клавиша ведения огня.

    Args:
        controller: Синглтон-фасад управления низкоуровневым вводом мыши.
        pull_speed: Скорость стягивания (интервал от 1 до 20).
    """
    # Масштабирование условного параметра скорости в шаг пиксельного смещения
    move_y = max(1, int(pull_speed * 0.5))
    
    while True:
        with _rcs_state["rcs_lock"]:
            if not _rcs_state["is_active"]:
                break
        
        # Проверяем, удерживает ли пользователь кнопку ведения огня (LMB = 0)
        if is_button_pressed(0):
            try:
                controller.move(0, move_y)
            except Exception as exc:
                log_print("[RCS Thread Mouse Move Error]", exc)
        else:
            # Если кнопка отпущена, принудительно гасим флаг активности
            with _rcs_state["rcs_lock"]:
                _rcs_state["is_active"] = False
            break
            
        time.sleep(0.01)  # Фиксированный шаг дискретизации пулл-дауна (100 Гц)


def is_rcs_active() -> bool:
    """Возвращает текущий статус активности потока контроля отдачи.

    Returns:
        bool: True, если система в данный момент компенсирует отдачу.
    """
    with _rcs_state["rcs_lock"]:
        return bool(_rcs_state["is_active"])


def process_rcs(tracker: Any) -> bool:
    """Основной диспетчер подсистемы RCS (вызывается на каждый обработанный кадр).

    Проверяет условия включения функции в конфигурации, отслеживает длительность
    удержания кнопки мыши и при необходимости инициализирует асинхронный поток пулла.

    Args:
        tracker: Экземпляр родительского адаптера трекера.

    Returns:
        bool: Флаг активности подсистемы RCS в текущем такте.
    """
    if not getattr(config, "rcs_enabled", False):
        with _rcs_state["rcs_lock"]:
            _rcs_state["is_active"] = False
        return False

    left_pressed = is_button_pressed(0)  # 0 = Левая кнопка мыши (LMB)
    now = time.time()

    with _rcs_state["rcs_lock"]:
        if left_pressed:
            if _rcs_state["button_press_time"] is None:
                _rcs_state["button_press_time"] = now
                
            # Расчет длительности удержания кнопки мыши в миллисекундах
            hold_duration_ms = (now - _rcs_state["button_press_time"]) * 1000.0
            required_delay = float(getattr(config, "rcs_start_delay_ms", 100.0))

            # Поток активируется только после преодоления порога задержки (защита от мискликов)
            if hold_duration_ms >= required_delay and not _rcs_state["is_active"]:
                _rcs_state["is_active"] = True
                pull_speed = float(getattr(config, "rcs_pull_speed", 4.0))
                
                _rcs_state["rcs_thread"] = threading.Thread(
                    target=_rcs_pull_loop,
                    args=(tracker.controller, pull_speed),
                    daemon=True
                )
                _rcs_state["rcs_thread"].start()
        else:
            # Сброс временных якорей при высвобождении клавиши
            _rcs_state["button_press_time"] = None
            _rcs_state["is_active"] = False

        return _rcs_state["is_active"]


def check_y_release() -> bool:
    """Проверяет необходимость временного отключения оси Y для логики аимбота.

    Используется для исключения конфликтов между жестким пулл-дауном отдачи
    и вертикальной доводкой мыши OpenCV-аимботом в первые секунды зажима.

    Returns:
        bool: True, если в данный момент ось Y должна быть освобождена.
    """
    if not getattr(config, "rcs_enabled", False) or not getattr(config, "rcs_release_y", False):
        with _y_release_state["release_lock"]:
            _y_release_state["is_released"] = False
            _y_release_state["release_start_time"] = None
        return False
    
    release_duration = float(getattr(config, "rcs_release_y_duration", 1.0))
    # Бруствер безопасности: ограничение интервала в диапазоне от 0.1 до 5.0 секунд
    release_duration = max(0.1, min(5.0, release_duration))
    
    now = time.time()
    left_button_pressed = is_button_pressed(0)
    
    with _y_release_state["release_lock"]:
        if left_button_pressed:
            # Если зажим только начался, взводим стартовый якорь времени
            if _y_release_state["release_start_time"] is None:
                _y_release_state["release_start_time"] = now
                _y_release_state["release_duration"] = release_duration
                _y_release_state["is_released"] = True
            else:
                # Проверяем, укладывается ли текущий зажим в лимит окна разблокировки
                elapsed = now - _y_release_state["release_start_time"]
                if elapsed < release_duration:
                    _y_release_state["is_released"] = True
                else:
                    # Окно разблокировки истекло, возвращаем полный контроль пулл-дауну
                    _y_release_state["is_released"] = False
        else:
            # Кнопка отпущена — обнуляем триггеры
            _y_release_state["is_released"] = False
            _y_release_state["release_start_time"] = None
            
        return _y_release_state["is_released"]