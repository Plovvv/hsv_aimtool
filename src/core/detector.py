"""Модуль детекции объектов по HSV-маске (HSV Contour Detector).

Захватывает прямоугольную область экрана вокруг центрального пикселя монитора,
применяет цветовой фильтр в пространстве HSV, находит контуры подходящих объектов
и возвращает их метрики, рассчитывая текущую производительность (FPS).
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import cv2
import mss
import numpy as np


@dataclass
class DetectedObject:
    """Контейнер геометрических параметров найденного объекта.

    Attributes:
        cx: Абсолютная координата центра объекта по оси X на кадре захвата.
        cy: Абсолютная координата центра объекта по оси Y на кадре захвата.
        x: Левая граница ограничивающего прямоугольника (bounding box).
        y: Верхняя граница ограничивающего прямоугольника (bounding box).
        w: Ширина ограничивающего прямоугольника.
        h: Высота ограничивающего прямоугольника.
        area: Геометрическая площадь контура объекта в пикселях.
    """
    cx: int
    cy: int
    x: int
    y: int
    w: int
    h: int
    area: float


@dataclass
class DetectionResult:
    """Контейнер результатов обработки одного кадра детекции.

    Attributes:
        frame_bgr: Исходная OpenCV матрица изображения в формате BGR.
        frame_mask: Бинарная маска после применения порогового HSV-фильтра.
        frame_overlay: Изображение с наложенной маской и подсветкой целей.
        objects: Список найденных объектов, отсортированных по площади контура.
        fps: Текущая частота обработки кадров (кадры в секунду).
        detect_ms: Время полной обработки кадра в миллисекундах.
    """
    frame_bgr: Optional[np.ndarray] = None
    frame_mask: Optional[np.ndarray] = None
    frame_overlay: Optional[np.ndarray] = None
    objects: List[DetectedObject] = field(default_factory=list)
    fps: float = 0.0
    detect_ms: float = 0.0


class HSVDetector:
    """Потоковый детектор объектов на основе пороговой фильтрации цвета.

    Выполняет захват экрана, фильтрацию и выделение контуров в фоновом режиме.
    """

    def __init__(self, config: Any) -> None:
        """Инициализирует детектор экрана и структуры синхронизации.

        Args:
            config: Глобальный экземпляр класса Config с HSV-параметрами.
        """
        self._cfg = config
        self._sct = mss.mss()
        self._running: bool = False
        self._thread: Optional[threading.Thread] = None
        self._lock: threading.Lock = threading.Lock()
        self._latest_result: DetectionResult = DetectionResult()

    def start(self) -> None:
        """Запускает фоновый поток циклического захвата и обработки экрана."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Безопасно останавливает фоновый поток детектора."""
        self._running = False
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=0.5)

    def get_latest_result(self) -> DetectionResult:
        """Возвращает снапшот последнего обработанного кадра детекции.

        Returns:
            DetectionResult: Объект с кадрами, списком целей и метриками FPS.
        """
        with self._lock:
            return self._latest_result

    def _get_capture_zone(self) -> Dict[str, int]:
        """Рассчитывает координаты зоны захвата mss вокруг центра экрана.

        Returns:
            Dict[str, int]: Словарь с ключами top, left, width, height для mss.
        """
        # Динамически получаем разрешение из синглтона конфигурации
        monitor = self._sct.monitors[1]
        screen_cx = monitor["width"] // 2
        screen_cy = monitor["height"] // 2

        zone_w = self._cfg.cam_width
        zone_h = self._cfg.cam_height

        left = screen_cx - (zone_w // 2) + self._cfg.cam_offset_x
        top = screen_cy - (zone_h // 2) + self._cfg.cam_offset_y

        return {
            "top": int(top),
            "left": int(left),
            "width": int(zone_w),
            "height": int(zone_h)
        }

    def _create_hsv_mask(self, frame_bgr: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Применяет пороговый HSV-фильтр и генерирует цветной оверлей отладки.

        Args:
            frame_bgr: Матрица исходного изображения BGR.

        Returns:
            Tuple[np.ndarray, np.ndarray]: Бинарная маска кадра и цветной оверлей.
        """
        hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
        lower = np.array([
            self._cfg.hsv_min_h,
            self._cfg.hsv_min_s,
            self._cfg.hsv_min_v
        ], dtype=np.uint8)

        upper = np.array([
            self._cfg.hsv_max_h,
            self._cfg.hsv_max_s,
            self._cfg.hsv_max_v
        ], dtype=np.uint8)

        mask = cv2.inRange(hsv, lower, upper)

        # Отрисовка декоративного полупрозрачного оверлея
        overlay = frame_bgr.copy()
        overlay[mask == 0] = (overlay[mask == 0] * 0.25).astype(np.uint8)
        overlay[mask > 0] = np.clip(
            overlay[mask > 0].astype(np.int16) + [0, 80, 0], 0, 255
        ).astype(np.uint8)

        return mask, overlay

    def _find_objects(self, mask: np.ndarray) -> List[DetectedObject]:
        """Находит замкнутые контуры объектов по бинарной маске.

        Args:
            mask: Бинарная маска кадра.

        Returns:
            List[DetectedObject]: Список найденных объектов, отсортированных
                по убыванию площади контура.
        """
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        objects: List[DetectedObject] = []

        for cnt in contours:
            area = float(cv2.contourArea(cnt))
            if area < self._cfg.min_contour_area:
                continue

            x, y, w, h = cv2.boundingRect(cnt)
            cx = x + w // 2
            cy = y + h // 2

            objects.append(DetectedObject(
                cx=int(cx),
                cy=int(cy),
                x=int(x),
                y=int(y),
                w=int(w),
                h=int(h),
                area=area
            ))

        return sorted(objects, key=lambda o: o.area, reverse=True)

    def _process_frame(self) -> DetectionResult:
        """Выполняет один полный такт конвейера: захват -> маска -> детекция контуров.

        Returns:
            DetectionResult: Сформированный результат анализа кадра.
        """
        result = DetectionResult()
        t_start = time.perf_counter()

        zone = self._get_capture_zone()
        img = self._sct.grab(zone)

        # Конвертация кадра из BGRA (формат mss) в BGR (формат OpenCV)
        frame_bgr = np.array(img, dtype=np.uint8)[:, :, :3]
        result.frame_bgr = frame_bgr

        mask, overlay = self._create_hsv_mask(frame_bgr)
        result.frame_mask = mask
        result.frame_overlay = overlay
        result.objects = self._find_objects(mask)

        t_end = time.perf_counter()
        result.detect_ms = float((t_end - t_start) * 1000.0)

        return result

    def _loop(self) -> None:
        """Главный рабочий цикл фонового потока детектора с подсчетом FPS."""
        last_time = time.perf_counter()
        frame_count = 0
        current_fps = 0.0

        while self._running:
            try:
                res = self._process_frame()
                frame_count += 1

                now = time.perf_counter()
                elapsed = now - last_time
                if elapsed >= 1.0:
                    current_fps = float(frame_count / elapsed)
                    frame_count = 0
                    last_time = now

                res.fps = current_fps

                with self._lock:
                    self._latest_result = res

            except Exception:
                # Безопасный пропуск кадра при ошибках выделения памяти/захвата
                time.sleep(0.001)

            # Минимальная разгрузка процессора
            time.sleep(0.001)