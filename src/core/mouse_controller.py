"""Модуль фонового контроллера наведения (Mouse Controller Engine).

Координирует совместную работу фонового HSV-детектора и адаптера трекера целей,
снимая метрики активности подсистем (аимбот, автовыстрел, триггербот, RCS)
и транслируя их в потокобезопасный статус для интерфейса пользователя.
"""

import threading
import time
from typing import Any, Dict, Optional

from src.core.aim_tracker import AimTrackerAdapter
from src.utils.logger import logger


class MouseController:
    """Фоновый контроллер конвейера автоматического наведения.

    Опрашивает снапшоты детектора контуров и передает их в подсистему CVM
    для расчета относительных смещений курсора мыши.
    """

    def __init__(self, config: Any, detector: Any) -> None:
        """Инициализирует контроллер наведения, трекер целей и структуры статуса.

        Args:
            config: Глобальный синглтон конфигурации Config.
            detector: Экземпляр фонового HSV-детектора контуров экрана.
        """
        self._cfg = config
        self._detector = detector
        self._tracker: AimTrackerAdapter = AimTrackerAdapter()
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock: threading.Lock = threading.Lock()
        
        # Начальная структура телеметрии для вывода на главный экран GUI
        self._status: Dict[str, Any] = {
            "aim_active": False,
            "last_dx": 0,
            "last_dy": 0,
            "trigger_fired": False,
            "autofire_fired": False,
            "rcs_active": False,
            "backend": "SendInput",
            "connected": False,
        }

    @property
    def tracker(self) -> AimTrackerAdapter:
        """Возвращает экземпляр адаптера трекера целей CVM.

        Returns:
            AimTrackerAdapter: Связанный объект логики удержания цели.
        """
        return self._tracker

    def start(self) -> None:
        """Запускает фоновый рабочий поток итеративного цикла наведения."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.log("Aim engine (CVM) активен", "OK")

    def stop(self) -> None:
        """Останавливает рабочий поток контроллера и сбрасывает ресурсы мыши."""
        self._running = False
        self._tracker.stop()
        try:
            from src.utils.mouse import Mouse
            # Безопасный вызов очистки синглтона мыши, если реализован
            if hasattr(Mouse, "cleanup"):
                Mouse.cleanup()
        except Exception:
            pass

    def get_status(self) -> Dict[str, Any]:
        """Потокобезопасно возвращает текущий снапшот телеметрии систем наводки.

        Returns:
            Dict[str, Any]: Копия словаря флагов активности подсистем.
        """
        with self._lock:
            return dict(self._status)

    def _loop(self) -> None:
        """Главный рабочий цикл: чтение кадра -> обработка трекером -> логирование."""
        while self._running:
            t0 = time.perf_counter()
            try:
                # Получаем последний обработанный кадр из детектора
                result = self._detector.get_latest_result()
                
                # Передаем цели, параметры кадра и изображение в CVM-конвейер
                status = self._tracker.update(
                    targets=result.objects,
                    frame=result,  # result выступает контейнером разрешения xres/yres
                    img=result.frame_bgr
                )
                
                # Дополняем статус техническими параметрами бэкенда ввода
                from src.utils.mouse import is_connected, state
                status["backend"] = str(state.active_backend)
                status["connected"] = bool(is_connected())
                
                with self._lock:
                    self._status = status
                    
            except Exception as exc:
                logger.log(f"Aim error: {exc}", "ERROR")

            # Вычисление времени сна для удержания стабильного шага итераций
            elapsed = time.perf_counter() - t0
            sleep_time = 0.001 - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            else:
                time.sleep(0.0001)  # Защита от зависания при падении FPS