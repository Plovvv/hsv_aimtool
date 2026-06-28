"""Модуль классического режима наведения (Normal Aim Engine).

Рассчитывает угловые и пиксельные смещения до выбранного контура цели,
выполняет сглаживание траектории движения мыши с учетом DPI/чувствительности,
интегрирует компенсацию отдачи (RCS) и передает данные в асинхронную очередь.
"""

import math
import queue
from typing import Any, List, Optional, Tuple

from src.aim_system.RCS import check_y_release, process_rcs
from src.aim_system.Triggerbot import process_triggerbot
from src.utils.activation import check_aimbot_activation, get_active_aim_fov
from src.utils.config import config
from src.utils.debug_logger import log_move


def _queue_move(tracker: Any, dx: float, dy: float, delay: float = 0.0, drop_oldest: bool = True) -> bool:
    """Потокобезопасно помещает рассчитанное смещение в очередь команд мыши.

    Args:
        tracker: Экземпляр родительского адаптера трекера с очередью move_queue.
        dx: Шаг перемещения по оси X.
        dy: Шаг перемещения по оси Y.
        delay: Задержка выполнения шага в секундах.
        drop_oldest: Если True, при переполнении очереди удаляет старый элемент.

    Returns:
        bool: True, если элемент успешно добавлен в очередь.
    """
    item = (float(dx), float(dy), max(0.0, float(delay)))
    try:
        tracker.move_queue.put_nowait(item)
        return True
    except queue.Full:
        if drop_oldest:
            try:
                tracker.move_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                tracker.move_queue.put_nowait(item)
                return True
            except queue.Full:
                return False
        return False


def calculate_movement(dx: float, dy: float, sens: float, dpi: int) -> Tuple[float, float]:
    """Переводит пиксельное расстояние на экране в физические отсчеты (counts) мыши.

    Использует классическую формулу перерасчета CVM на основе шага окружности.

    Args:
        dx: Дельта координат по оси X в пикселях.
        dy: Дельта координат по оси Y в пикселях.
        sens: Внутриигровая чувствительность мыши.
        dpi: Аппаратное разрешение сенсора мыши (DPI).

    Returns:
        Tuple[float, float]: Физическое смещение для мыши по осям X и Y.
    """
    cm_per_rev = 54.54 / max(float(sens), 0.01)
    count_per_cm = float(dpi) / 2.54
    deg_per_count = 360.0 / (cm_per_rev * count_per_cm)
    return dx * deg_per_count, dy * deg_per_count


def _apply_normal_aim(dx: float, dy: float, distance: float, tracker: Any) -> None:
    """Рассчитывает сглаженный шаг перемещения и добавляет его в очередь вывода.

    Args:
        dx: Полная пиксельная дельта до цели по X.
        dy: Полная пиксельная дельта до цели по Y.
        distance: Евклидово расстояние от прицела до цели в пикселях.
        tracker: Ссылка на родительский адаптер трекера для синхронизации параметров.
    """
    _ = distance  # Аргумент сохранен для совместимости с интерфейсом вызовов CVM
    
    # Расчет шага сглаживания на основе динамических коэффициентов
    smooth = max(float(tracker.mouse_smoothness), 1.0)
    step_x = (dx * float(tracker.normal_x_speed)) / smooth
    step_y = (dy * float(tracker.normal_y_speed)) / smooth

    # Применение тонкой компенсации остаточных смещений (Residual Filtering)
    rx, ry = tracker._normal_residual
    total_x = step_x + rx
    total_y = step_y + ry

    int_x = int(total_x)
    int_y = int(total_y)

    tracker._normal_residual = (total_x - int_x, total_y - int_y)

    if int_x != 0 or int_y != 0:
        log_move(int_x, int_y)
        _queue_move(tracker, int_x, int_y)


def process_aim_frame(
    targets: List[Any],
    frame: Any,
    img: Any,
    tracker: Any,
    targets_trigger: Optional[List[Any]] = None,
) -> None:
    """Основная точка входа обработки кадра наведения (вызывается на каждый кадр детекции).

    Выполняет итеративный анализ геометрических целей, рассчитывает векторы
    сопровождения с учетом RCS, а затем передает управление в подсистему триггербота.

    Args:
        targets: Список обнаруженных объектов для наведения.
        frame: Контейнер метаданных текущего кадра (свойства xres, yres).
        img: OpenCV матрица кадра для отладки.
        tracker: Экземпляр родительского адаптера трекера.
        targets_trigger: Опциональный список объектов, передаваемый напрямую в триггербот.
    """
    aim_enabled = bool(getattr(config, "enableaim", False))
    always_on = bool(getattr(config, "aim_always_on", False))
    selected_btn = getattr(config, "aim_binding", None)
    activation_type = getattr(config, "aim_binding_mode", "Hold")

    center_x = int(frame.xres // 2)
    center_y = int(frame.yres // 2)

    # Интеграция подсистемы контроля отдачи (RCS)
    rcs_active = process_rcs(tracker)

    if targets:
        # Выбираем приоритетную цель (ближайшую к центру перекрестия)
        best_target = min(targets, key=lambda t: t[2])
        cx, cy, distance_to_center = best_target[0], best_target[1], best_target[2]

        main_fov = float(get_active_aim_fov(is_sec=False, fallback=tracker.fovsize))

        if distance_to_center <= main_fov and aim_enabled:
            # Проверяем удержание клавиши активации аимбота
            active = always_on or (
                selected_btn is not None
                and check_aimbot_activation(selected_btn, activation_type, is_sec=False)
            )
            if active:
                aim_offset_x = float(getattr(config, "aim_offsetX", tracker.aim_offsetX))
                aim_offset_y = float(getattr(config, "aim_offsetY", tracker.aim_offsetY))
                
                dx = (cx + aim_offset_x) - center_x
                dy = (cy + aim_offset_y) - center_y
                
                # Изолируем ось Y, если активен RCS или взведен триггер отсечки
                if rcs_active or check_y_release():
                    dy = 0
                    
                _apply_normal_aim(dx, dy, distance_to_center, tracker)

    # Передача конвейера обработки кадра в подсистему автоматического выстрела
    if getattr(config, "enabletb", False):
        try:
            tracker.last_trigger_status = process_triggerbot(
                targets=targets,
                frame_info=frame,
                img=img,
                tracker_obj=tracker,
                targets_trigger=targets_trigger,
            )
        except Exception as exc:
            from src.utils.debug_logger import log_print
            log_print("[Normal Aim Triggerbot Invocation Error]", exc)