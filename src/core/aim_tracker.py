"""Модуль адаптера трекера целей (Aim Tracker Adapter).

Служит связующим звеном между HSV-детектором контуров и логикой наведения
CVM aim_system. Управляет асинхронной очередью сглаженных перемещений мыши.
"""

import queue
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

import numpy as np

from src.aim_system.normal import process_aim_frame
from src.utils.config import config
from src.utils.mouse import Mouse, tick_movement_lock_manager


@dataclass
class FrameInfo:
    """Контейнер параметров кадра для совместимости с Triggerbot CVM API.

    Attributes:
        xres: Горизонтальное разрешение области сканирования.
        yres: Вертикальное разрешение области сканирования.
    """
    xres: int
    yres: int


class AimTrackerAdapter:
    """Адаптер трекера целей под HSV-детектор контуров.

    Attributes:
        controller: Singleton-фасад управления вводом мыши.
        move_queue: Потокобезопасная очередь относительных смещений курсора.
    """

    def __init__(self) -> None:
        """Инициализирует трекер, параметры сглаживания и запускает поток мыши."""
        self.controller = Mouse()
        self.move_queue: queue.Queue = queue.Queue(maxsize=50)
        self._move_batch_size: int = 4
        self._stop_event = threading.Event()
        self._move_thread = threading.Thread(
            target=self._process_move_queue,
            daemon=True
        )
        self._move_thread.start()
        self._sync_tracker_params()
        self.last_trigger_status: str = "IDLE"
        self._normal_residual: Tuple[float, float] = (0.0, 0.0)

    def _sync_tracker_params(self) -> None:
        """Синхронизирует внутренние коэффициенты скорости с CVM конфигурацией."""
        self.normal_x_speed = float(getattr(config, "aim_speed_x", 0.35))
        self.normal_y_speed = float(getattr(config, "aim_speed_y", 0.35))
        self.mouse_smoothness = float(getattr(config, "aim_smoothness", 4.0))

    def stop(self) -> None:
        """Останавливает фоновый поток обработки очереди перемещений мыши."""
        self._stop_event.set()
        if self._move_thread.is_alive():
            self._move_thread.join(timeout=0.2)

    def add_movement(self, dx: float, dy: float) -> None:
        """Потокобезопасно добавляет относительное смещение в очередь наводки.

        Args:
            dx: Смещение по оси X.
            dy: Смещение по оси Y.
        """
        if not config.enableaim:
            return
        try:
            self.move_queue.put_nowait((float(dx), float(dy)))
        except queue.Full:
            try:
                self.move_queue.get_nowait()
                self.move_queue.put_nowait((float(dx), float(dy)))
            except queue.Empty:
                pass

    def _process_move_queue(self) -> None:
        """Фоновый рабочий поток извлечения и исполнения пакетов перемещения мыши."""
        while not self._stop_event.is_set():
            try:
                dx, dy = self.move_queue.get(timeout=0.01)
                self.controller.move(dx, dy)
                self.move_queue.task_done()
            except queue.Empty:
                continue
            except Exception:
                pass

    def update(self, targets: List[Any], frame: FrameInfo, img: np.ndarray) -> Dict[str, Any]:
        """Обновляет состояние трекера целей на основе текущего кадра.

        Вызывает основной конвейер фильтрации CVM и рассчитывает флаги
        состояния для вывода телеметрии в GUI.

        Args:
            targets: Список обнаруженных контуров целей.
            frame: Спецификация разрешения кадра FrameInfo.
            img: Исходная OpenCV матрица изображения кадра.

        Returns:
            Dict[str, Any]: Словарь текущих флагов активности подсистем наводки.
        """
        self._sync_tracker_params()
        center_x = int(frame.xres // 2)
        center_y = int(frame.yres // 2)

        status = {
            "aim_active": False,
            "trigger_status": "IDLE",
            "trigger_fired": False,
            "autofire_fired": False,
            "rcs_active": False,
        }

        tick_mouse_loops()

        if targets and config.enableaim:
            best = min(targets, key=lambda t: t[2])
            status["aim_active"] = best[2] <= config.fovsize

        process_aim_frame(targets, frame, img, self, targets_trigger=targets)

        trig_status = getattr(self, "last_trigger_status", "IDLE")
        status["trigger_status"] = trig_status
        status["trigger_fired"] = trig_status in (
            "BURST_STARTED", "BURSTING", "BURST_IN_PROGRESS",
        ) or str(trig_status).startswith("BURST_STARTED")

        if config.autofire_enabled and targets:
            status["autofire_fired"] = self._run_autofire(targets, center_x, center_y)

        from src.aim_system.RCS import is_rcs_active
        status["rcs_active"] = is_rcs_active()

        return status

    _last_autofire: float = 0.0
    _autofire_burst: int = 0

    def _run_autofire(self, targets: List[Any], cx: int, cy: int) -> bool:
        """Проверяет условия и выполняет автовыстрел по ближайшей цели внутри FOV.

        Args:
            targets: Список обнаруженных контуров целей.
            cx: Центр экрана по X.
            cy: Центр экрана по Y.

        Returns:
            bool: True, если команда выстрела была успешно передана мыши.
        """
        best = min(targets, key=lambda t: t[2])
        if best[2] > config.autofire_radius:
            self._autofire_burst = 0
            return False

        now = time.time() * 1000
        burst_ok = False
        if self._autofire_burst == 0:
            if now - self._last_autofire >= config.autofire_cooldown_ms:
                burst_ok = True
        else:
            burst_ok = True

        if burst_ok:
            if self._autofire_burst == 0:
                self._autofire_burst = np.random.randint(
                    config.autofire_burst_min,
                    config.autofire_burst_max + 1
                )
            self.controller.click()
            self._autofire_burst -= 1
            if self._autofire_burst <= 0:
                self._last_autofire = now
                self._autofire_burst = 0
            return True

        return False