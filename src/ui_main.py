"""Модуль главного графического интерфейса приложения HSV Color Detector."""

import json
import os
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

import customtkinter as ctk
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageTk

from src.core.detector import DetectionResult, HSVDetector
from src.core.mouse_controller import MouseController
from src.utils.config import AIM_KEY_BINDINGS, COLOR_PRESETS, config
from src.utils.logger import logger
from src.utils.mouse import (
    BACKENDS,
    connect_to_makcu,
    disconnect_all,
    get_active_backend,
    get_last_connect_error,
    is_connected,
    switch_backend,
    switch_to_4m,
    test_move,
)

# ===========================================================================
# ТЕМА - NEON DARK
# ===========================================================================
C_BG = "#050D1A"
C_SIDEBAR = "#030B15"
C_SURFACE = "#0A1628"
C_SURFACE2 = "#0D1F38"
C_ACCENT = "#00FFB2"
C_ACCENT2 = "#00C8FF"
C_ACCENT_DIM = "#007A56"
C_HOVER = "#00FFB230"
C_TEXT = "#C8E6FF"
C_TEXT_DIM = "#4A6A8A"
C_BORDER = "#0D3A5C"
C_DANGER = "#FF4D6D"
C_WARN = "#FFD166"
C_SUCCESS = "#00FF88"
C_PURPLE = "#BF5FFF"

FONT_MONO = ("Consolas", 11)
FONT_BOLD = ("Consolas", 11, "bold")
FONT_TITLE = ("Consolas", 20, "bold")
FONT_SMALL = ("Consolas", 9)
FONT_LABEL = ("Consolas", 10)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")


# ===========================================================================
# ВСПОМОГАТЕЛЬНЫЕ ВИДЖЕТЫ
# ===========================================================================

class GlowLabel(tk.Canvas):
    """Компонент текстовой метки с многослойным эффектом неонового свечения."""

    def __init__(self, master, text: str, font=FONT_TITLE,
                 text_color=C_ACCENT, glow_color=C_ACCENT, **kw):
        super().__init__(master, bg=C_BG, highlightthickness=0, **kw)
        self._text = text
        self._font = font
        self._text_color = text_color
        self._glow_color = glow_color
        self.bind("<Configure>", lambda e: self._draw())
        self.after(50, self._draw)

    def _draw(self) -> None:
        """Выполняет послойную отрисовку размытия тени и основного текста."""
        self.delete("all")
        w = self.winfo_width() or 300
        h = self.winfo_height() or 60

        # Генерация эффекта свечения через полупрозрачные смещенные слои
        offsets = [3, 2, 1]
        alphas = ["20", "40", "60"]
        for off, alpha in zip(offsets, alphas):
            color = self._glow_color + alpha
            try:
                self.create_text(w // 2 + off, h // 2 + off,
                                 text=self._text, font=self._font,
                                 fill=color, anchor="center")
                self.create_text(w // 2 - off, h // 2 - off,
                                 text=self._text, font=self._font,
                                 fill=color, anchor="center")
            except Exception:
                pass

        self.create_text(w // 2, h // 2, text=self._text,
                         font=self._font, fill=self._text_color, anchor="center")


class NeonFrame(ctk.CTkFrame):
    """Стилизованная контентная панель с боковым цветовым маркером заголовка."""

    def __init__(self, master, title: str = "", accent: str = C_ACCENT, **kw):
        kw.setdefault("fg_color", C_SURFACE)
        kw.setdefault("corner_radius", 12)
        kw.setdefault("border_width", 1)
        kw.setdefault("border_color", C_BORDER)
        super().__init__(master, **kw)
        self._accent = accent
        if title:
            self._build_header(title)

    def _build_header(self, title: str) -> None:
        """Создает верхнюю плашку панели с текстовым заголовком."""
        hdr = ctk.CTkFrame(self, fg_color=C_SURFACE2, corner_radius=0, height=36)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        accent_bar = ctk.CTkFrame(hdr, fg_color=self._accent, width=3, corner_radius=0)
        accent_bar.pack(side="left", fill="y")

        ctk.CTkLabel(hdr, text=title.upper(), font=FONT_BOLD,
                     text_color=self._accent, anchor="w").pack(side="left", padx=12)


class HSVSliderRow(ctk.CTkFrame):
    """Блок спаренных слайдеров (MIN/MAX) для прецизионной настройки канала HSV."""

    def __init__(self, master, label: str, min_val: int, max_val: int,
                 from_: int, to: int, accent: str = C_ACCENT,
                 on_change=None, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)

        self._on_change = on_change
        self._var_lo = tk.IntVar(value=min_val)
        self._var_hi = tk.IntVar(value=max_val)
        self._from = from_
        self._to = to

        # Индикатор наименования канала
        ctk.CTkLabel(self, text=label, font=FONT_BOLD,
                     text_color=accent, width=28, anchor="w").grid(
            row=0, column=0, rowspan=2, padx=(0, 10))

        # Слайдер минимального значения (MIN)
        ctk.CTkLabel(self, text="MIN", font=FONT_SMALL,
                     text_color=C_TEXT_DIM).grid(row=0, column=1, sticky="w")
        self._sl_lo = ctk.CTkSlider(
            self, from_=from_, to=to, variable=self._var_lo,
            progress_color=accent, button_color=accent,
            button_hover_color=C_TEXT, fg_color=C_SURFACE2,
            command=self._on_slide)
        self._sl_lo.grid(row=0, column=2, padx=8, sticky="ew")
        self._lbl_lo = ctk.CTkLabel(self, text=str(min_val),
                                    font=FONT_LABEL, text_color=C_TEXT, width=38)
        self._lbl_lo.grid(row=0, column=3)

        # Слайдер максимального значения (MAX)
        ctk.CTkLabel(self, text="MAX", font=FONT_SMALL,
                     text_color=C_TEXT_DIM).grid(row=1, column=1, sticky="w")
        self._sl_hi = ctk.CTkSlider(
            self, from_=from_, to=to, variable=self._var_hi,
            progress_color=accent, button_color=accent,
            button_hover_color=C_TEXT, fg_color=C_SURFACE2,
            command=self._on_slide)
        self._sl_hi.grid(row=1, column=2, padx=8, sticky="ew")
        self._lbl_hi = ctk.CTkLabel(self, text=str(max_val),
                                    font=FONT_LABEL, text_color=C_TEXT, width=38)
        self._lbl_hi.grid(row=1, column=3)

        self.columnconfigure(2, weight=1)

    def _on_slide(self, _=None) -> None:
        """Синхронизирует текстовые значения с текущим положением ползунков."""
        lo = int(self._var_lo.get())
        hi = int(self._var_hi.get())
        self._lbl_lo.configure(text=str(lo))
        self._lbl_hi.configure(text=str(hi))
        if self._on_change:
            self._on_change()

    def get(self) -> tuple:
        """Возвращает текущие выбранные границы диапазона (min, max)."""
        return int(self._var_lo.get()), int(self._var_hi.get())

    def set(self, lo: int, hi: int) -> None:
        """Задает границы диапазона программным путем."""
        self._var_lo.set(lo)
        self._var_hi.set(hi)
        self._lbl_lo.configure(text=str(lo))
        self._lbl_hi.configure(text=str(hi))


# ===========================================================================
# ГЛАВНОЕ ОКНО ПРИЛОЖЕНИЯ
# ===========================================================================

class MainApp(ctk.CTk):
    """Координатор графического интерфейса и подсистем детекции/управления."""

    def __init__(self) -> None:
        super().__init__()
        self.title("HSV Color Detector")
        self.geometry("1200x820")
        self.minsize(900, 650)
        self.configure(fg_color=C_BG)
        self.overrideredirect(True)

        self._active_tab = "General"
        self._detector = HSVDetector(config)
        self._detector.start()
        self._mouse = MouseController(config, self._detector)
        self._mouse.start()
        logger.log("Приложение запущено", "OK")
        logger.log("Детектор HSV активен", "OK")

        self._preview_photo = None
        self._mask_photo = None
        self._drag_x = 0
        self._drag_y = 0
        self._is_max = False
        self._restore_geo = ""

        self._build_layout()
        self.after(33, self._update_preview_loop)
        self.after(500, self._update_debug_loop)
        self.after(200, self._update_stats_loop)

    def _build_layout(self) -> None:
        """Формирует каркас интерфейса: заголовок, боковую панель и рабочую область."""
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_title_bar()
        self._build_sidebar()
        
        self.content = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C_BORDER,
            scrollbar_button_hover_color=C_ACCENT_DIM)
        self.content.grid(row=1, column=1, sticky="nsew", padx=20, pady=16)
        self._show_tab("General")

    def _build_title_bar(self) -> None:
        """Создает кастомную панель управления окном (Title Bar)."""
        bar = ctk.CTkFrame(self, height=38, fg_color=C_SIDEBAR, corner_radius=0)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_propagate(False)

        left = ctk.CTkFrame(bar, fg_color="transparent")
        left.pack(side="left", padx=16)

        dot = ctk.CTkFrame(left, width=8, height=8, fg_color=C_ACCENT, corner_radius=4)
        dot.pack(side="left", pady=13)

        ctk.CTkLabel(left, text="  HSV", font=("Consolas", 12, "bold"), text_color=C_ACCENT).pack(side="left")
        ctk.CTkLabel(left, text=" COLOR DETECTOR", font=("Consolas", 12), text_color=C_TEXT_DIM).pack(side="left")
        ctk.CTkLabel(left, text="  v1.0", font=FONT_SMALL, text_color=C_TEXT_DIM).pack(side="left")

        # Применение DRY: Корректное назначение индивидуальных hover_color для кнопок управления
        for sym, cmd, hover_color in [
            ("✕", self._on_close, C_DANGER),
            ("□", self._toggle_max, C_SURFACE),
            ("_", self._on_min, C_SURFACE),
        ]:
            ctk.CTkButton(
                bar, text=sym, width=32, height=32,
                fg_color="transparent", hover_color=hover_color,
                text_color=C_TEXT_DIM, font=("Consolas", 12),
                command=cmd, corner_radius=0
            ).pack(side="right")

        bar.bind("<Button-1>", self._start_drag)
        bar.bind("<B1-Motion>", self._do_drag)
        left.bind("<Button-1>", self._start_drag)
        left.bind("<B1-Motion>", self._do_drag)

    def _start_drag(self, e) -> None:
        """Фиксирует начальные координаты мыши при старте перемещения окна."""
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _do_drag(self, e) -> None:
        """Перемещает окно вслед за курсором мыши."""
        self.geometry(f"+{e.x_root - self._drag_x}+{e.y_root - self._drag_y}")

    def _on_close(self) -> None:
        """Безопасно останавливает фоновые потоки и сохраняет конфигурацию перед выходом."""
        self._mouse.stop()
        self._detector.stop()
        config.save()
        self.destroy()

    def _on_min(self) -> None:
        """Сворачивает приложение в панель задач."""
        self.overrideredirect(False)
        self.iconify()
        self.bind("<Map>", lambda e: self.overrideredirect(True))

    def _toggle_max(self) -> None:
        """Переключает полноэкранный режим приложения."""
        if self._is_max:
            self.geometry(self._restore_geo)
        else:
            self._restore_geo = self.geometry()
            w = self.winfo_screenwidth()
            h = self.winfo_screenheight()
            self.geometry(f"{w}x{h}+0+0")
        self._is_max = not self._is_max

    def _build_sidebar(self) -> None:
        """Создает боковую навигационную панель и статус-бар."""
        self.sidebar = ctk.CTkFrame(self, width=220, fg_color=C_SIDEBAR, corner_radius=0)
        self.sidebar.grid(row=1, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)

        ctk.CTkFrame(self.sidebar, width=1, fg_color=C_BORDER).pack(side="right", fill="y")

        brand = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(20, 6))
        ctk.CTkLabel(brand, text="HSV", font=("Consolas", 32, "bold"), text_color=C_ACCENT, anchor="w").pack(anchor="w")
        ctk.CTkLabel(brand, text="Color Detector", font=("Consolas", 10), text_color=C_TEXT_DIM, anchor="w").pack(anchor="w")

        ctk.CTkFrame(self.sidebar, height=1, fg_color=C_BORDER).pack(fill="x", pady=(4, 10))

        nav = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        nav.pack(fill="x", padx=10)
        self._nav_btns: dict = {}
        
        tabs = [
            ("General", "⚙", self._show_tab),
            ("HSV Range", "🎨", self._show_tab),
            ("Mouse", "🖱", self._show_tab),
            ("Preview", "👁", self._show_tab),
            ("Debug", "🔧", self._show_tab),
        ]
        for name, icon, cmd in tabs:
            btn = self._make_nav_btn(nav, f" {icon} {name}", name, cmd)
            btn.pack(fill="x", pady=2)
            self._nav_btns[name] = btn

        self._build_sidebar_status()
        self._set_active_nav("General")

    def _make_nav_btn(self, parent, text: str, tab_name: str, cmd) -> ctk.CTkButton:
        """Создаёт кнопку навигации."""
        return ctk.CTkButton(
            parent, text=text, anchor="w",
            font=FONT_MONO, height=40, corner_radius=8,
            fg_color="transparent", hover_color=C_SURFACE,
            text_color=C_TEXT_DIM, border_width=0,
            command=lambda: cmd(tab_name))

    def _set_active_nav(self, name: str) -> None:
        """Выделяет активную кнопку навигации."""
        for n, btn in self._nav_btns.items():
            if n == name:
                btn.configure(fg_color=C_SURFACE2, text_color=C_ACCENT,
                               border_width=1, border_color=C_ACCENT_DIM)
            else:
                btn.configure(fg_color="transparent", text_color=C_TEXT_DIM,
                               border_width=0)

    def _build_sidebar_status(self) -> None:
        """Строит панель статуса в нижней части сайдбара."""
        bottom = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        bottom.pack(side="bottom", fill="x", padx=14, pady=16)

        ctk.CTkFrame(bottom, height=1, fg_color=C_BORDER).pack(fill="x", pady=(0, 10))

        self._lbl_fps = ctk.CTkLabel(bottom, text="FPS: --",
                                     font=FONT_LABEL, text_color=C_TEXT_DIM,
                                     anchor="w")
        self._lbl_fps.pack(fill="x")

        self._lbl_objects = ctk.CTkLabel(bottom, text="Objects: 0",
                                         font=FONT_LABEL, text_color=C_TEXT_DIM,
                                         anchor="w")
        self._lbl_objects.pack(fill="x")

        self._lbl_ms = ctk.CTkLabel(bottom, text="Detect: -- ms",
                                    font=FONT_LABEL, text_color=C_TEXT_DIM,
                                    anchor="w")
        self._lbl_ms.pack(fill="x")

        # Статус детектора
        status_row = ctk.CTkFrame(bottom, fg_color="transparent")
        status_row.pack(fill="x", pady=(8, 0))
        self._dot_status = ctk.CTkFrame(status_row, width=8, height=8,
                                        fg_color=C_SUCCESS, corner_radius=4)
        self._dot_status.pack(side="left")
        ctk.CTkLabel(status_row, text="  Detector ACTIVE",
                     font=FONT_SMALL, text_color=C_SUCCESS).pack(side="left")

    # ------------------------------------------------------------------
    # Вкладки
    # ------------------------------------------------------------------

    def _clear_content(self) -> None:
        """Очищает область контента."""
        for w in self.content.winfo_children():
            w.destroy()

    def _show_tab(self, name: str) -> None:
        """Переключает активную вкладку."""
        self._active_tab = name
        self._set_active_nav(name)
        self._clear_content()
        {
            "General":   self._build_general,
            "HSV Range": self._build_hsv,
            "Mouse":     self._build_mouse,
            "Preview":   self._build_preview,
            "Debug":     self._build_debug,
        }[name]()

    # ------------------------------------------------------------------
    # Вкладка General
    # ------------------------------------------------------------------

    def _build_general(self) -> None:
        """Строит вкладку General - общие настройки."""
        # Заголовок
        hdr = NeonFrame(self.content, title="General Settings")
        hdr.pack(fill="x", pady=(0, 12))

        body = ctk.CTkFrame(hdr, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=12)

        # FOV size
        self._add_slider_row(body, "Capture FOV (px)",
                             config.fov_size, 100, 600,
                             lambda v: setattr(config, "fov_size", int(v)),
                             accent=C_ACCENT)

        # FPS
        self._add_slider_row(body, "Capture FPS",
                             config.capture_fps, 10, 120,
                             lambda v: setattr(config, "capture_fps", int(v)),
                             accent=C_ACCENT2)

        # Min contour area
        self._add_slider_row(body, "Min Contour Area",
                             config.min_contour_area, 10, 500,
                             lambda v: setattr(config, "min_contour_area", int(v)),
                             accent=C_PURPLE)

        # Визуализация
        vis = NeonFrame(self.content, title="Visualization Options", accent=C_ACCENT2)
        vis.pack(fill="x", pady=(0, 12))
        vbody = ctk.CTkFrame(vis, fg_color="transparent")
        vbody.pack(fill="x", padx=16, pady=12)

        checks = [
            ("Show Bounding Box", "show_bounding_box", C_ACCENT),
            ("Show Contours",     "show_contours",     C_ACCENT2),
            ("Show Center Dot",   "show_center_dot",   C_WARN),
            ("Mask Overlay",      "show_mask_overlay", C_SUCCESS),
        ]
        for i, (label, attr, color) in enumerate(checks):
            var = tk.BooleanVar(value=getattr(config, attr))
            cb = ctk.CTkCheckBox(vbody, text=label, variable=var,
                                 font=FONT_MONO, text_color=C_TEXT,
                                 fg_color=color, hover_color=color,
                                 checkmark_color=C_BG,
                                 command=lambda a=attr, v=var:
                                 setattr(config, a, v.get()))
            cb.grid(row=i // 2, column=i % 2, padx=12, pady=6, sticky="w")

        # Профили цветов
        preset_card = NeonFrame(self.content, title="Color Presets", accent=C_WARN)
        preset_card.pack(fill="x", pady=(0, 12))
        pbody = ctk.CTkFrame(preset_card, fg_color="transparent")
        pbody.pack(fill="x", padx=16, pady=12)

        preset_colors = {
            "red": "#FF4D6D", "purple": C_PURPLE,
            "yellow": C_WARN, "blue": C_ACCENT2,
            "green": C_SUCCESS, "custom": C_TEXT_DIM,
        }
        col = 0
        for name, color in preset_colors.items():
            ctk.CTkButton(
                pbody, text=name.capitalize(), width=90, height=34,
                fg_color=C_SURFACE2, hover_color=C_SURFACE,
                text_color=color, font=FONT_BOLD,
                border_width=1, border_color=color,
                corner_radius=8,
                command=lambda n=name: self._apply_preset(n)
            ).grid(row=0, column=col, padx=5, pady=4)
            col += 1

        # Кнопки сохранения
        btn_row = ctk.CTkFrame(self.content, fg_color="transparent")
        btn_row.pack(fill="x", pady=4)

        ctk.CTkButton(btn_row, text="💾  Save Config", width=160, height=38,
                      fg_color=C_ACCENT_DIM, hover_color=C_ACCENT,
                      text_color=C_BG, font=FONT_BOLD, corner_radius=10,
                      command=self._save_config).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="📂  Load Config", width=160, height=38,
                      fg_color=C_SURFACE2, hover_color=C_SURFACE,
                      text_color=C_ACCENT, font=FONT_BOLD, corner_radius=10,
                      border_width=1, border_color=C_BORDER,
                      command=self._load_config).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="↺  Reset HSV", width=160, height=38,
                      fg_color=C_SURFACE2, hover_color=C_SURFACE,
                      text_color=C_WARN, font=FONT_BOLD, corner_radius=10,
                      border_width=1, border_color=C_BORDER,
                      command=self._reset_hsv).pack(side="left", padx=6)

    def _add_slider_row(self, parent, label: str, val, from_, to,
                        cmd, accent=C_ACCENT) -> None:
        """Добавляет строку с одним слайдером и числовым значением."""
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=5)
        ctk.CTkLabel(row, text=label, font=FONT_LABEL,
                     text_color=C_TEXT, width=180, anchor="w").pack(side="left")
        lbl_val = ctk.CTkLabel(row, text=str(int(val)), font=FONT_BOLD,
                               text_color=accent, width=48)
        lbl_val.pack(side="right")
        var = tk.DoubleVar(value=val)

        def on_change(v):
            lbl_val.configure(text=str(int(float(v))))
            cmd(float(v))

        sl = ctk.CTkSlider(row, from_=from_, to=to, variable=var,
                           progress_color=accent, button_color=accent,
                           button_hover_color=C_TEXT, fg_color=C_SURFACE2,
                           command=on_change)
        sl.pack(side="left", fill="x", expand=True, padx=10)

    # ------------------------------------------------------------------
    # Вкладка HSV Range
    # ------------------------------------------------------------------

    def _build_hsv(self) -> None:
        """Строит вкладку настройки HSV-диапазонов."""
        # Карточка H
        h_card = NeonFrame(self.content, title="H - Hue (Цвет)", accent="#FF6B9D")
        h_card.pack(fill="x", pady=(0, 10))
        hb = ctk.CTkFrame(h_card, fg_color="transparent")
        hb.pack(fill="x", padx=16, pady=12)
        self._sl_h = HSVSliderRow(hb, "H", config.hsv_min_h, config.hsv_max_h,
                                  0, 179, accent="#FF6B9D",
                                  on_change=self._on_hsv_change)
        self._sl_h.pack(fill="x")

        # Полоса цветового круга
        self._draw_hue_bar(h_card)

        # Карточка S
        s_card = NeonFrame(self.content, title="S - Saturation (Насыщенность)",
                           accent=C_WARN)
        s_card.pack(fill="x", pady=(0, 10))
        sb = ctk.CTkFrame(s_card, fg_color="transparent")
        sb.pack(fill="x", padx=16, pady=12)
        self._sl_s = HSVSliderRow(sb, "S", config.hsv_min_s, config.hsv_max_s,
                                  0, 255, accent=C_WARN,
                                  on_change=self._on_hsv_change)
        self._sl_s.pack(fill="x")

        # Карточка V
        v_card = NeonFrame(self.content, title="V - Value (Яркость)", accent=C_ACCENT2)
        v_card.pack(fill="x", pady=(0, 10))
        vb = ctk.CTkFrame(v_card, fg_color="transparent")
        vb.pack(fill="x", padx=16, pady=12)
        self._sl_v = HSVSliderRow(vb, "V", config.hsv_min_v, config.hsv_max_v,
                                  0, 255, accent=C_ACCENT2,
                                  on_change=self._on_hsv_change)
        self._sl_v.pack(fill="x")

        # Живой предпросмотр цвета
        color_preview = NeonFrame(self.content, title="Live Color Preview",
                                  accent=C_ACCENT)
        color_preview.pack(fill="x", pady=(0, 10))
        self._color_canvas = tk.Canvas(color_preview, height=60,
                                       bg=C_SURFACE, highlightthickness=0)
        self._color_canvas.pack(fill="x", padx=16, pady=10)
        self._update_color_preview()

    def _draw_hue_bar(self, parent) -> None:
        """Рисует радугу оттенков Hue на Canvas."""
        canvas = tk.Canvas(parent, height=18, bg=C_SURFACE,
                           highlightthickness=0)
        canvas.pack(fill="x", padx=16, pady=(0, 8))
        canvas.update_idletasks()
        w = canvas.winfo_width() or 600
        for i in range(w):
            hue = int(179 * i / w)
            bgr = cv2.cvtColor(
                np.array([[[hue, 255, 220]]], dtype=np.uint8), cv2.COLOR_HSV2RGB)
            r, g, b = int(bgr[0, 0, 0]), int(bgr[0, 0, 1]), int(bgr[0, 0, 2])
            canvas.create_line(i, 0, i, 18, fill=f"#{r:02x}{g:02x}{b:02x}")

    def _on_hsv_change(self) -> None:
        """Применяет новые HSV-значения из слайдеров в конфиг."""
        if not hasattr(self, "_sl_h"):
            return
        config.hsv_min_h, config.hsv_max_h = self._sl_h.get()
        config.hsv_min_s, config.hsv_max_s = self._sl_s.get()
        config.hsv_min_v, config.hsv_max_v = self._sl_v.get()
        config.color_preset = "custom"
        self._update_color_preview()

    def _update_color_preview(self) -> None:
        """Обновляет полосу предпросмотра выбранного цвета."""
        if not hasattr(self, "_color_canvas"):
            return
        canvas = self._color_canvas
        canvas.update_idletasks()
        w = canvas.winfo_width() or 600
        h = 60

        # Средний Hue диапазона
        mid_h = (config.hsv_min_h + config.hsv_max_h) // 2
        mid_s = (config.hsv_min_s + config.hsv_max_s) // 2
        mid_v = (config.hsv_min_v + config.hsv_max_v) // 2

        bgr = cv2.cvtColor(
            np.array([[[mid_h, mid_s, mid_v]]], dtype=np.uint8),
            cv2.COLOR_HSV2RGB)
        r, g, b = int(bgr[0, 0, 0]), int(bgr[0, 0, 1]), int(bgr[0, 0, 2])
        color = f"#{r:02x}{g:02x}{b:02x}"

        canvas.delete("all")
        canvas.create_rectangle(0, 0, w, h, fill=color, outline="")
        canvas.create_text(w // 2, h // 2,
                           text=f"HSV({mid_h}, {mid_s}, {mid_v})",
                           font=FONT_BOLD, fill="#000000" if mid_v > 128 else "#ffffff")

    # ------------------------------------------------------------------
    # Вкладка Mouse
    # ------------------------------------------------------------------

    def _build_mouse(self) -> None:
        """Строит вкладку Mouse - подключение MAKCU/SendInput + aim функции."""
        # --- Подключение (CVM mouse backend) ---
        conn_card = NeonFrame(self.content, title="Mouse Connection", accent=C_PURPLE)
        conn_card.pack(fill="x", pady=(0, 12))
        cbody = ctk.CTkFrame(conn_card, fg_color="transparent")
        cbody.pack(fill="x", padx=16, pady=12)

        row1 = ctk.CTkFrame(cbody, fg_color="transparent")
        row1.pack(fill="x", pady=4)
        ctk.CTkLabel(row1, text="Backend", font=FONT_LABEL,
                     text_color=C_TEXT, width=120, anchor="w").pack(side="left")
        self._mouse_api_var = tk.StringVar(value=config.mouse_api)
        ctk.CTkOptionMenu(
            row1,
            values=["SendInput", "Serial"],
            variable=self._mouse_api_var, width=180, height=32,
            fg_color=C_SURFACE2, button_color=C_PURPLE,
            font=FONT_MONO,
            command=self._on_mouse_backend_change,
        ).pack(side="left", padx=8)
        ctk.CTkLabel(
            row1,
            text="SendInput = тест Windows  |  Serial = MAKCU USB",
            font=FONT_SMALL, text_color=C_TEXT_DIM,
        ).pack(side="left", padx=8)

        row2 = ctk.CTkFrame(cbody, fg_color="transparent")
        row2.pack(fill="x", pady=4)
        ctk.CTkLabel(row2, text="COM mode", font=FONT_LABEL,
                     text_color=C_TEXT, width=120, anchor="w").pack(side="left")
        self._serial_mode_var = tk.StringVar(value=config.serial_port_mode)
        ctk.CTkOptionMenu(
            row2, values=["Auto", "Manual"], variable=self._serial_mode_var,
            width=120, height=32, fg_color=C_SURFACE2, button_color=C_PURPLE,
            font=FONT_MONO,
            command=lambda v: setattr(config, "serial_port_mode", v),
        ).pack(side="left", padx=8)
        ctk.CTkLabel(row2, text="COM port", font=FONT_SMALL,
                     text_color=C_TEXT_DIM).pack(side="left", padx=(12, 4))
        self._serial_port_entry = ctk.CTkEntry(
            row2, width=100, height=32, fg_color=C_SURFACE2,
            text_color=C_TEXT, font=FONT_MONO,
            placeholder_text="COM3")
        self._serial_port_entry.pack(side="left")
        if config.serial_port:
            self._serial_port_entry.insert(0, config.serial_port)

        btn_row = ctk.CTkFrame(cbody, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 4))
        ctk.CTkButton(
            btn_row, text="🔌 Connect", width=120, height=34,
            fg_color=C_ACCENT_DIM, hover_color=C_ACCENT,
            text_color=C_BG, font=FONT_BOLD, corner_radius=8,
            command=self._on_mouse_connect,
        ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(
            btn_row, text="⏏ Disconnect", width=120, height=34,
            fg_color=C_SURFACE2, hover_color=C_SURFACE,
            text_color=C_DANGER, font=FONT_BOLD, corner_radius=8,
            border_width=1, border_color=C_DANGER,
            command=self._on_mouse_disconnect,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row, text="↗ Test Move", width=120, height=34,
            fg_color=C_SURFACE2, hover_color=C_SURFACE,
            text_color=C_ACCENT2, font=FONT_BOLD, corner_radius=8,
            border_width=1, border_color=C_BORDER,
            command=self._on_mouse_test_move,
        ).pack(side="left", padx=6)
        ctk.CTkButton(
            btn_row, text="4M Baud", width=100, height=34,
            fg_color=C_SURFACE2, hover_color=C_SURFACE,
            text_color=C_WARN, font=FONT_BOLD, corner_radius=8,
            border_width=1, border_color=C_BORDER,
            command=self._on_mouse_switch_4m,
        ).pack(side="left", padx=6)

        self._lbl_conn_status = ctk.CTkLabel(
            cbody, text=self._format_conn_status(),
            font=FONT_MONO, text_color=C_TEXT_DIM, anchor="w")
        self._lbl_conn_status.pack(fill="x", pady=(8, 0))

        # --- Включатели функций ---
        toggle_card = NeonFrame(self.content, title="Mouse Features", accent=C_ACCENT)
        toggle_card.pack(fill="x", pady=(0, 12))
        tbody = ctk.CTkFrame(toggle_card, fg_color="transparent")
        tbody.pack(fill="x", padx=16, pady=12)
        tbody.columnconfigure((0, 1), weight=1)

        features = [
            ("Aimbot",     "aimbot_enabled",     C_ACCENT),
            ("Triggerbot", "triggerbot_enabled", C_DANGER),
            ("Autofire",   "autofire_enabled",   C_WARN),
            ("RCS",        "rcs_enabled",        C_ACCENT2),
        ]
        for i, (label, attr, color) in enumerate(features):
            var = tk.BooleanVar(value=getattr(config, attr))
            cb = ctk.CTkCheckBox(
                tbody, text=label, variable=var,
                font=FONT_BOLD, text_color=C_TEXT,
                fg_color=color, hover_color=color,
                checkmark_color=C_BG,
                command=lambda a=attr, v=var: self._on_mouse_toggle(a, v.get()),
            )
            cb.grid(row=i // 2, column=i % 2, padx=12, pady=8, sticky="w")

        # Aimbot
        aim_card = NeonFrame(self.content, title="Aimbot (CVM Normal)", accent=C_ACCENT)
        aim_card.pack(fill="x", pady=(0, 10))
        aim_body = ctk.CTkFrame(aim_card, fg_color="transparent")
        aim_body.pack(fill="x", padx=16, pady=12)

        self._add_slider_row(
            aim_body, "Smoothness (1=fast, 100=smooth)",
            config.aim_smoothness, 1, 100,
            lambda v: setattr(config, "aim_smoothness", int(v)),
            accent=C_ACCENT,
        )
        self._add_slider_row(
            aim_body, "Aim FOV Radius (px)",
            config.aim_fov_radius, 10, 300,
            lambda v: setattr(config, "aim_fov_radius", int(v)),
            accent=C_ACCENT,
        )
        self._add_slider_row(
            aim_body, "X Speed",
            config.aim_x_speed * 100, 5, 300,
            lambda v: setattr(config, "aim_x_speed", float(v) / 100),
            accent=C_ACCENT,
        )
        self._add_slider_row(
            aim_body, "Y Speed",
            config.aim_y_speed * 100, 5, 300,
            lambda v: setattr(config, "aim_y_speed", float(v) / 100),
            accent=C_ACCENT,
        )
        self._add_slider_row(
            aim_body, "Offset X",
            config.aim_offset_x, -50, 50,
            lambda v: setattr(config, "aim_offset_x", int(v)),
            accent=C_ACCENT,
        )
        self._add_slider_row(
            aim_body, "Offset Y (head)",
            config.aim_offset_y, -80, 20,
            lambda v: setattr(config, "aim_offset_y", int(v)),
            accent=C_ACCENT,
        )
        self._add_slider_row(
            aim_body, "In-game Sens ×100",
            config.in_game_sens * 100, 1, 100,
            lambda v: setattr(config, "in_game_sens", float(v) / 100),
            accent=C_ACCENT,
        )
        self._add_slider_row(
            aim_body, "Mouse DPI",
            config.mouse_dpi, 400, 3200,
            lambda v: setattr(config, "mouse_dpi", int(v)),
            accent=C_ACCENT,
        )

        key_row = ctk.CTkFrame(aim_body, fg_color="transparent")
        key_row.pack(fill="x", pady=8)
        ctk.CTkLabel(key_row, text="Activation Key", font=FONT_LABEL,
                     text_color=C_TEXT, width=180, anchor="w").pack(side="left")
        self._aim_key_var = tk.StringVar(value=config.aim_key)
        ctk.CTkOptionMenu(
            key_row, values=list(AIM_KEY_BINDINGS.keys()),
            variable=self._aim_key_var, width=160, height=32,
            fg_color=C_SURFACE2, button_color=C_ACCENT_DIM,
            button_hover_color=C_ACCENT, dropdown_fg_color=C_SURFACE,
            font=FONT_MONO, command=self._on_aim_key_change,
        ).pack(side="left", padx=10)

        # Triggerbot
        trig_card = NeonFrame(self.content, title="Triggerbot (CVM HSV ROI)", accent=C_DANGER)
        trig_card.pack(fill="x", pady=(0, 10))
        trig_body = ctk.CTkFrame(trig_card, fg_color="transparent")
        trig_body.pack(fill="x", padx=16, pady=12)

        self._add_slider_row(
            trig_body, "Trigger Delay (ms)",
            config.trigger_delay_ms, 0, 500,
            lambda v: setattr(config, "trigger_delay_ms", int(v)),
            accent=C_DANGER,
        )
        self._add_slider_row(
            trig_body, "Trigger FOV (px)",
            config.trigger_radius, 3, 120,
            lambda v: setattr(config, "trigger_radius", int(v)),
            accent=C_DANGER,
        )
        self._add_slider_row(
            trig_body, "Cooldown (ms)",
            config.trigger_cooldown_ms, 50, 1000,
            lambda v: setattr(config, "trigger_cooldown_ms", int(v)),
            accent=C_DANGER,
        )
        self._add_slider_row(
            trig_body, "Confirm Frames",
            config.trigger_confirm_frames, 1, 10,
            lambda v: setattr(config, "trigger_confirm_frames", int(v)),
            accent=C_DANGER,
        )
        self._add_slider_row(
            trig_body, "Burst Min / Max",
            config.trigger_burst_max, 1, 10,
            lambda v: (
                setattr(config, "trigger_burst_min", 1),
                setattr(config, "trigger_burst_max", int(v)),
            ),
            accent=C_DANGER,
        )

        # Autofire
        auto_card = NeonFrame(self.content, title="Autofire", accent=C_WARN)
        auto_card.pack(fill="x", pady=(0, 10))
        auto_body = ctk.CTkFrame(auto_card, fg_color="transparent")
        auto_body.pack(fill="x", padx=16, pady=12)

        self._add_slider_row(
            auto_body, "Fire Delay (ms)",
            config.autofire_delay_ms, 30, 500,
            lambda v: setattr(config, "autofire_delay_ms", int(v)),
            accent=C_WARN,
        )
        self._add_slider_row(
            auto_body, "Detection Radius (px)",
            config.autofire_radius, 5, 120,
            lambda v: setattr(config, "autofire_radius", int(v)),
            accent=C_WARN,
        )
        self._add_slider_row(
            auto_body, "Burst Count (0=unlimited)",
            config.autofire_burst, 0, 20,
            lambda v: setattr(config, "autofire_burst", int(v)),
            accent=C_WARN,
        )

        # RCS
        rcs_card = NeonFrame(self.content, title="RCS - Recoil Control (CVM thread)", accent=C_ACCENT2)
        rcs_card.pack(fill="x", pady=(0, 10))
        rcs_body = ctk.CTkFrame(rcs_card, fg_color="transparent")
        rcs_body.pack(fill="x", padx=16, pady=12)

        self._add_slider_row(
            rcs_body, "Pull Speed (1-20)",
            config.rcs_strength, 1, 20,
            lambda v: setattr(config, "rcs_strength", int(v)),
            accent=C_ACCENT2,
        )
        self._add_slider_row(
            rcs_body, "Activation Delay (ms)",
            config.rcs_activation_delay_ms, 0, 500,
            lambda v: setattr(config, "rcs_activation_delay_ms", int(v)),
            accent=C_ACCENT2,
        )
        self._add_slider_row(
            rcs_body, "Rapid Click Threshold (ms)",
            config.rcs_rapid_click_ms, 50, 500,
            lambda v: setattr(config, "rcs_rapid_click_ms", int(v)),
            accent=C_ACCENT2,
        )

        # Live status
        status_card = NeonFrame(self.content, title="Live Aim Status", accent=C_SUCCESS)
        status_card.pack(fill="x", pady=(0, 10))
        sbody = ctk.CTkFrame(status_card, fg_color="transparent")
        sbody.pack(fill="x", padx=16, pady=12)

        self._lbl_mouse_status = ctk.CTkLabel(
            sbody, text="Idle", font=FONT_BOLD, text_color=C_TEXT_DIM, anchor="w")
        self._lbl_mouse_status.pack(fill="x")
        self._lbl_mouse_delta = ctk.CTkLabel(
            sbody, text="Backend: --", font=FONT_LABEL, text_color=C_TEXT_DIM, anchor="w")
        self._lbl_mouse_delta.pack(fill="x", pady=(4, 0))

        hint = ctk.CTkLabel(
            self.content,
            text="Логика из CVM-colorBot: Normal aim + HSV triggerbot + RCS thread.\n"
                 "SendInput - тест без MAKCU. Serial - подключение MAKCU (km.move).",
            font=FONT_SMALL, text_color=C_TEXT_DIM, justify="left")
        hint.pack(anchor="w", padx=4, pady=(4, 0))

    def _format_conn_status(self) -> str:
        if is_connected():
            return f"● Connected  |  Backend: {get_active_backend()}"
        err = get_last_connect_error()
        return f"○ Disconnected  |  {err}" if err else "○ Disconnected - нажмите Connect"

    def _on_mouse_backend_change(self, api: str) -> None:
        config.mouse_api = api
        logger.log(f"Mouse backend: {api}", "INFO")
        if hasattr(self, "_lbl_conn_status"):
            self._lbl_conn_status.configure(text=self._format_conn_status())

    def _on_mouse_connect(self) -> None:
        config.mouse_api = self._mouse_api_var.get()
        config.serial_port_mode = self._serial_mode_var.get()
        config.serial_port = self._serial_port_entry.get().strip()
        ok, err = switch_backend(
            config.mouse_api,
            serial_port_mode=config.serial_port_mode,
            serial_port=config.serial_port,
        )
        if ok:
            logger.log(f"Подключено: {get_active_backend()}", "OK")
        else:
            logger.log(f"Ошибка подключения: {err or get_last_connect_error()}", "ERROR")
        if hasattr(self, "_lbl_conn_status"):
            self._lbl_conn_status.configure(text=self._format_conn_status())

    def _on_mouse_disconnect(self) -> None:
        disconnect_all(config.mouse_api)
        logger.log("Mouse отключён", "WARN")
        if hasattr(self, "_lbl_conn_status"):
            self._lbl_conn_status.configure(text=self._format_conn_status())

    def _on_mouse_test_move(self) -> None:
        if not is_connected():
            ok, _ = switch_backend(config.mouse_api)
            if not ok:
                logger.log("Сначала подключите mouse backend", "ERROR")
                return
        test_move()
        logger.log("Test move (+100,+100)", "OK")

    def _on_mouse_switch_4m(self) -> None:
        if switch_to_4m():
            logger.log("MAKCU переключён на 4M baud", "OK")
        else:
            logger.log("Не удалось переключить на 4M", "WARN")
        if hasattr(self, "_lbl_conn_status"):
            self._lbl_conn_status.configure(text=self._format_conn_status())

    def _on_mouse_toggle(self, attr: str, value: bool) -> None:
        """Обработчик включения/выключения mouse-функций."""
        setattr(config, attr, value)
        name = attr.replace("_enabled", "").capitalize()
        state = "ON" if value else "OFF"
        logger.log(f"{name}: {state}", "OK" if value else "WARN")

    def _on_aim_key_change(self, key: str) -> None:
        """Меняет клавишу активации aimbot."""
        config.aim_key = key
        logger.log(f"Aim key: {key}", "INFO")

    # ------------------------------------------------------------------
    # Вкладка Preview
    # ------------------------------------------------------------------

    def _build_preview(self) -> None:
        """Строит вкладку живого предпросмотра детекции."""
        top_row = ctk.CTkFrame(self.content, fg_color="transparent")
        top_row.pack(fill="x", pady=(0, 12))
        top_row.columnconfigure((0, 1), weight=1)

        # Оверлей
        overlay_card = NeonFrame(top_row, title="HSV Overlay", accent=C_ACCENT)
        overlay_card.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._canvas_overlay = tk.Canvas(overlay_card, width=380, height=300,
                                         bg="#000000", highlightthickness=0)
        self._canvas_overlay.pack(padx=10, pady=10)

        # Маска
        mask_card = NeonFrame(top_row, title="Binary Mask", accent=C_ACCENT2)
        mask_card.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        self._canvas_mask = tk.Canvas(mask_card, width=380, height=300,
                                      bg="#000000", highlightthickness=0)
        self._canvas_mask.pack(padx=10, pady=10)

        # Статистика объектов
        stats_card = NeonFrame(self.content, title="Detected Objects",
                               accent=C_SUCCESS)
        stats_card.pack(fill="x", pady=(0, 12))
        self._stats_frame = ctk.CTkFrame(stats_card, fg_color="transparent")
        self._stats_frame.pack(fill="x", padx=16, pady=8)

        self._lbl_obj_count = ctk.CTkLabel(
            self._stats_frame,
            text="Objects found: 0", font=FONT_BOLD,
            text_color=C_SUCCESS)
        self._lbl_obj_count.pack(side="left", padx=16)

        self._lbl_best_area = ctk.CTkLabel(
            self._stats_frame,
            text="Largest area: --", font=FONT_LABEL,
            text_color=C_TEXT_DIM)
        self._lbl_best_area.pack(side="left", padx=16)

        self._lbl_best_pos = ctk.CTkLabel(
            self._stats_frame,
            text="Best target: --", font=FONT_LABEL,
            text_color=C_ACCENT)
        self._lbl_best_pos.pack(side="left", padx=16)

    def _update_preview_loop(self) -> None:
        """Периодически обновляет превью-кадры из детектора."""
        if self._active_tab == "Preview":
            self._refresh_preview()
        self.after(33, self._update_preview_loop)

    def _refresh_preview(self) -> None:
        """Отрисовывает последний кадр детектора на Canvas."""
        result: DetectionResult = self._detector.get_latest()

        if result.frame_overlay is not None:
            frame = self._draw_annotations(result)
            self._preview_photo = self._bgr_to_tkphoto(frame, 380, 300)
            if hasattr(self, "_canvas_overlay"):
                self._canvas_overlay.create_image(0, 0, anchor="nw",
                                                  image=self._preview_photo)

        if result.frame_mask is not None and hasattr(self, "_canvas_mask"):
            mask_rgb = cv2.cvtColor(result.frame_mask, cv2.COLOR_GRAY2RGB)
            # Раскрасим маску в неоновый зелёный
            colored = np.zeros_like(mask_rgb)
            colored[result.frame_mask > 0] = [0, 255, 178]
            self._mask_photo = self._bgr_to_tkphoto(colored, 380, 300)
            self._canvas_mask.create_image(0, 0, anchor="nw",
                                           image=self._mask_photo)

        if hasattr(self, "_lbl_obj_count"):
            n = len(result.objects)
            color = C_SUCCESS if n > 0 else C_TEXT_DIM
            self._lbl_obj_count.configure(
                text=f"Objects found: {n}", text_color=color)
            if result.objects:
                best = result.objects[0]
                self._lbl_best_area.configure(
                    text=f"Largest area: {int(best.area)} px²")
                self._lbl_best_pos.configure(
                    text=f"Best target: ({best.cx}, {best.cy})")
            else:
                self._lbl_best_area.configure(text="Largest area: --")
                self._lbl_best_pos.configure(text="Best target: --")

    def _draw_annotations(self, result: DetectionResult) -> np.ndarray:
        """
        Рисует аннотации на оверлей-кадре.

        Args:
            result: Результат детекции.

        Returns:
            Кадр BGR с нарисованными рамками, точками и т.д.
        """
        frame = result.frame_overlay.copy()
        fov = config.fov_size

        # Линии перекрестия по центру
        cx, cy = fov // 2, fov // 2
        cv2.line(frame, (cx - 20, cy), (cx + 20, cy), (0, 255, 178), 1)
        cv2.line(frame, (cx, cy - 20), (cx, cy + 20), (0, 255, 178), 1)

        # FOV-рамка
        cv2.rectangle(frame, (2, 2), (fov - 2, fov - 2), (20, 60, 40), 1)

        for i, obj in enumerate(result.objects):
            is_best = i == 0
            color = (0, 255, 140) if is_best else (0, 180, 100)
            thickness = 2 if is_best else 1

            if config.show_bounding_box:
                cv2.rectangle(frame,
                              (obj.x, obj.y),
                              (obj.x + obj.w, obj.y + obj.h),
                              color, thickness)
                # Уголки bounding box (красивее чем просто рамка)
                lc = 8
                for px, py in [(obj.x, obj.y),
                                (obj.x + obj.w, obj.y),
                                (obj.x, obj.y + obj.h),
                                (obj.x + obj.w, obj.y + obj.h)]:
                    dx = 1 if px == obj.x else -1
                    dy = 1 if py == obj.y else -1
                    cv2.line(frame, (px, py), (px + dx * lc, py), color, 2)
                    cv2.line(frame, (px, py), (px, py + dy * lc), color, 2)

            if config.show_center_dot:
                cv2.circle(frame, (obj.cx, obj.cy), 3, color, -1)
                if is_best:
                    cv2.circle(frame, (obj.cx, obj.cy), 8, color, 1)

            # Метка с площадью
            if is_best:
                cv2.putText(frame, f"#{i+1} {int(obj.area)}px",
                            (obj.x, obj.y - 5),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

        return frame

    @staticmethod
    def _bgr_to_tkphoto(bgr: np.ndarray, w: int, h: int) -> ImageTk.PhotoImage:
        """Конвертирует BGR numpy-массив в PhotoImage для Tkinter."""
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        pil = Image.fromarray(rgb).resize((w, h), Image.NEAREST)
        return ImageTk.PhotoImage(pil)

    # ------------------------------------------------------------------
    # Вкладка Debug
    # ------------------------------------------------------------------

    def _build_debug(self) -> None:
        """Строит вкладку отладки с логом и статистикой."""
        # Статистика
        stat_card = NeonFrame(self.content, title="Runtime Statistics",
                              accent=C_ACCENT2)
        stat_card.pack(fill="x", pady=(0, 10))
        stat_body = ctk.CTkFrame(stat_card, fg_color="transparent")
        stat_body.pack(fill="x", padx=16, pady=10)
        stat_body.columnconfigure((0, 1, 2, 3), weight=1)

        self._stat_labels: dict = {}
        stats = [
            ("FPS",          C_SUCCESS),
            ("Detect ms",    C_ACCENT),
            ("Objects",      C_WARN),
            ("FOV px",       C_ACCENT2),
        ]
        for i, (name, color) in enumerate(stats):
            card = ctk.CTkFrame(stat_body, fg_color=C_SURFACE2, corner_radius=8)
            card.grid(row=0, column=i, padx=6, pady=4, sticky="ew")
            ctk.CTkLabel(card, text=name, font=FONT_SMALL,
                         text_color=C_TEXT_DIM).pack(pady=(6, 0))
            lbl = ctk.CTkLabel(card, text="--", font=("Consolas", 18, "bold"),
                               text_color=color)
            lbl.pack(pady=(0, 6))
            self._stat_labels[name] = lbl

        # Текущий HSV
        hsv_card = NeonFrame(self.content, title="Current HSV Config",
                             accent=C_PURPLE)
        hsv_card.pack(fill="x", pady=(0, 10))
        hsv_body = ctk.CTkFrame(hsv_card, fg_color="transparent")
        hsv_body.pack(fill="x", padx=16, pady=8)
        self._lbl_hsv_cur = ctk.CTkLabel(
            hsv_body,
            text=self._format_hsv(),
            font=("Consolas", 12), text_color=C_TEXT)
        self._lbl_hsv_cur.pack(anchor="w")

        # Лог
        log_card = NeonFrame(self.content, title="Debug Log", accent=C_WARN)
        log_card.pack(fill="both", expand=True, pady=(0, 10))

        log_top = ctk.CTkFrame(log_card, fg_color="transparent")
        log_top.pack(fill="x", padx=16, pady=(6, 0))
        ctk.CTkButton(log_top, text="Clear", width=80, height=26,
                      fg_color=C_SURFACE2, hover_color=C_SURFACE,
                      text_color=C_DANGER, font=FONT_SMALL,
                      corner_radius=6, border_width=1, border_color=C_DANGER,
                      command=self._clear_log).pack(side="right")

        self._log_box = tk.Text(
            log_card, height=16, bg=C_SURFACE2, fg=C_TEXT,
            font=("Consolas", 9), insertbackground=C_ACCENT,
            relief="flat", bd=0, wrap="word",
            selectbackground=C_ACCENT_DIM, state="disabled")
        self._log_box.pack(fill="both", expand=True, padx=16, pady=(4, 12))

        # Цвета уровней лога
        self._log_box.tag_config("OK",    foreground=C_SUCCESS)
        self._log_box.tag_config("INFO",  foreground=C_TEXT)
        self._log_box.tag_config("WARN",  foreground=C_WARN)
        self._log_box.tag_config("ERROR", foreground=C_DANGER)

    def _format_hsv(self) -> str:
        """Форматирует текущие HSV-значения в читаемую строку."""
        return (f"H: [{config.hsv_min_h} – {config.hsv_max_h}]   "
                f"S: [{config.hsv_min_s} – {config.hsv_max_s}]   "
                f"V: [{config.hsv_min_v} – {config.hsv_max_v}]")

    def _update_debug_loop(self) -> None:
        """Периодически обновляет лог на вкладке Debug."""
        if self._active_tab == "Debug":
            self._refresh_log()
            if hasattr(self, "_lbl_hsv_cur"):
                self._lbl_hsv_cur.configure(text=self._format_hsv())
        self.after(500, self._update_debug_loop)

    def _refresh_log(self) -> None:
        """Перерисовывает содержимое лог-виджета."""
        if not hasattr(self, "_log_box"):
            return
        lines = logger.get_lines()
        self._log_box.configure(state="normal")
        self._log_box.delete("1.0", "end")
        for level, text in lines:
            self._log_box.insert("end", text + "\n", level)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _clear_log(self) -> None:
        """Очищает лог."""
        logger.clear()
        if hasattr(self, "_log_box"):
            self._log_box.configure(state="normal")
            self._log_box.delete("1.0", "end")
            self._log_box.configure(state="disabled")

    def _update_stats_loop(self) -> None:
        """Обновляет виджеты статистики в сайдбаре и на Debug."""
        result = self._detector.get_latest()
        fps = result.fps
        ms = result.detect_ms
        n = len(result.objects)

        # Сайдбар
        if hasattr(self, "_lbl_fps"):
            self._lbl_fps.configure(text=f"FPS: {fps:.0f}")
            self._lbl_objects.configure(text=f"Objects: {n}")
            self._lbl_ms.configure(text=f"Detect: {ms:.1f} ms")

        # Debug вкладка
        if hasattr(self, "_stat_labels"):
            self._stat_labels["FPS"].configure(text=f"{fps:.0f}")
            self._stat_labels["Detect ms"].configure(text=f"{ms:.1f}")
            self._stat_labels["Objects"].configure(text=str(n))
            self._stat_labels["FOV px"].configure(text=str(config.fov_size))

        # Mouse вкладка - live status
        if self._active_tab == "Mouse" and hasattr(self, "_lbl_mouse_status"):
            ms = self._mouse.get_status()
            parts = []
            if ms.get("aim_active"):
                parts.append("AIM")
            if ms.get("trigger_fired"):
                parts.append("TRIGGER")
            if ms.get("autofire_fired"):
                parts.append("AUTOFIRE")
            if ms.get("rcs_active"):
                parts.append("RCS")
            text = " | ".join(parts) if parts else "Idle"
            color = C_SUCCESS if parts else C_TEXT_DIM
            self._lbl_mouse_status.configure(text=text, text_color=color)
            backend = ms.get("backend", config.mouse_api)
            conn = "OK" if ms.get("connected") else "OFF"
            self._lbl_mouse_delta.configure(
                text=f"Backend: {backend}  |  Link: {conn}",
                text_color=C_ACCENT if ms.get("connected") else C_TEXT_DIM)
            if hasattr(self, "_lbl_conn_status"):
                self._lbl_conn_status.configure(text=self._format_conn_status())

        self.after(200, self._update_stats_loop)

    # ------------------------------------------------------------------
    # Действия
    # ------------------------------------------------------------------

    def _apply_preset(self, name: str) -> None:
        """Применяет цветовой пресет и обновляет слайдеры."""
        config.apply_preset(name)
        logger.log(f"Применён пресет: {name}", "OK")
        if self._active_tab == "HSV Range":
            self._show_tab("HSV Range")

    def _save_config(self) -> None:
        """Сохраняет конфигурацию в файл."""
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON config", "*.json")],
            initialfile="config.json")
        if path:
            config.save(path)
            logger.log(f"Конфиг сохранён: {os.path.basename(path)}", "OK")

    def _load_config(self) -> None:
        """Загружает конфигурацию из файла."""
        path = filedialog.askopenfilename(
            filetypes=[("JSON config", "*.json")])
        if path and config.load(path):
            logger.log(f"Конфиг загружен: {os.path.basename(path)}", "OK")
            self._show_tab(self._active_tab)

    def _reset_hsv(self) -> None:
        """Сбрасывает HSV к значениям по умолчанию."""
        config.reset_hsv()
        logger.log("HSV сброшен к значениям по умолчанию", "WARN")
        if self._active_tab == "HSV Range":
            self._show_tab("HSV Range")
