"""Модуль конфигурации приложения.

Объединяет параметры графического интерфейса пользователя и runtime-поля
компонентов aim_system, rcs и triggerbot.
"""

import json
import os

# Пресеты цветовой фильтрации HSV
COLOR_PRESETS: dict = {
    "red":    (0,   10,  120, 255, 120, 255),
    "purple": (130, 160, 80,  255, 80,  255),
    "yellow": (20,  35,  120, 255, 120, 255),
    "blue":   (100, 130, 100, 255, 100, 255),
    "green":  (40,  80,  80,  255, 80,  255),
    "custom": (0,   179, 0,   255, 0,   255),
}

# Маппинг клавиш интерфейса на внутренние биндинги CVM
AIM_KEY_BINDINGS: dict = {
    "always":   (True,  1),
    "rmb":      (False, 1),
    "lmb":      (False, 0),
    "shift":    (False, "SHIFT"),
    "xbutton1": (False, 3),
}


class Config:
    """Класс-хранилище настроек конфигурации детектора и модулей управления."""

    def __init__(self) -> None:
        """Инициализирует параметры конфигурации значениями по умолчанию."""
        # Базовые настройки детектора и захвата экрана
        self.hsv_min_h = 0
        self.hsv_max_h = 179
        self.hsv_min_s = 0
        self.hsv_max_s = 255
        self.hsv_min_v = 0
        self.hsv_max_v = 255

        self.fov_size = 200
        self.capture_fps = 60
        self.color_preset = "custom"
        self.min_contour_area = 30

        # Настройки отображения интерфейса (Визуализация)
        self.show_bounding_box = True
        self.show_contours = False
        self.show_center_dot = True
        self.show_mask_overlay = True
        self.theme = "neon"

        # Общие переключатели систем CVM
        self.aimbot_enabled = False
        self.triggerbot_enabled = False
        self.autofire_enabled = False
        self.rcs_enabled = False

        # Параметры сглаживания и смещения прицеливания (Aimbot)
        self.aim_smoothness = 25
        self.aim_fov_radius = 120
        self.aim_offset_x = 0
        self.aim_offset_y = 0
        self.aim_key = "always"

        # Вторичные параметры аимбота (Secondary Profiles)
        self.aim_smoothness_sec = 25
        self.aim_fov_radius_sec = 120
        self.aim_offset_x_sec = 0
        self.aim_offset_y_sec = 0
        self.aim_key_sec = "always"

        self.aim_mode = "smooth"
        self.aim_speed_multiplier = 1.0

        # Параметры задержек и радиуса (Triggerbot)
        self.trigger_delay_ms = 30
        self.trigger_radius = 15
        self.trigger_cooldown_ms = 150

        self.autofire_delay_ms = 100
        self.autofire_radius = 50

        # Runtime-поля, необходимые для совместимости со скриптами CVM-colorBot
        self.mouse_api = "SendInput"
        self.auto_connect_mouse_api = False
        self.serial_port = "Auto"
        self.serial_baudrate = 4000000

        self.selected_aim_btn = "always"
        self.aimbot_activation_type = "hold_enable"
        self.aim_fov_radius_always_visible = True

        self.selected_sec_aim_btn = "always"
        self.sec_aimbot_activation_type = "hold_enable"
        self.sec_aim_fov_radius_always_visible = False

        self.selected_tb_btn = "always"
        self.triggerbot_activation_type = "hold_enable"
        self.triggerbot_fov_radius_always_visible = False

        self.aim_method = "tracking"
        self.aim_update_period_ms = 1

        self.pid_kp = 0.4
        self.pid_ki = 0.02
        self.pid_kd = 0.05

        self.cf_weight_current = 0.7
        self.cf_weight_predicted = 0.3

        self.trigger_mode = "click"
        self.trigger_burst_min = 1
        self.trigger_burst_max = 3
        self.trigger_confirm_frames = 0

        self.rcs_strength = 50
        self.rcs_strength_y = 50
        self.rcs_strength_x = 10
        self.rcs_activation_delay_ms = 40
        self.rcs_rapid_click_ms = 200

        # Поля синхронизации кастинга типов для CVM
        # Поля синхронизации кастинга типов для CVM
        self.aim_smooth = int(self.aim_smoothness)
        self.aim_smooth_sec = int(self.aim_smoothness_sec)
        self.tb_delay = int(self.trigger_delay_ms)
        self.tb_cooldown = int(self.trigger_cooldown_ms)
        self.tbburst_count_min = int(self.trigger_burst_min)
        self.tbburst_count_max = int(self.trigger_burst_max)
        self.trigger_confirm_frames = int(self.trigger_confirm_frames)
        
        # Защита от падения при инициализации строки "always" в int
        try:
            self.selected_tb_btn = int(self.selected_tb_btn)
        except ValueError:
            # Оставляем строковое значение ("always" / "rmb"), если кастинг в int невозможен
            pass

        self.rcs_pull_speed = int(self.rcs_strength)
        self.rcs_activation_delay = int(self.rcs_activation_delay_ms)
        self.rcs_rapid_click_threshold = int(self.rcs_rapid_click_ms)

    def save(self, path: str = "config.json") -> None:
        """Сохраняет текущие настройки конфигурации в JSON-файл.

        Args:
            path: Путь к сохраняемому файлу конфигурации.
        """
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.__dict__, f, indent=4, ensure_ascii=False)

    def load(self, path: str = "config.json") -> bool:
        """Загружает настройки конфигурации из указанного JSON-файла.

        Args:
            path: Путь к загружаемому файлу конфигурации.

        Returns:
            bool: True в случае успешной загрузки, иначе False.
        """
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, value in data.items():
                if hasattr(self, key):
                    setattr(self, key, value)
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def apply_preset(self, preset: str) -> None:
        """Применяет параметры выбранного цветового пресета к диапазону HSV.

        Args:
            preset: Имя пресета из COLOR_PRESETS.
        """
        if preset in COLOR_PRESETS:
            h0, h1, s0, s1, v0, v1 = COLOR_PRESETS[preset]
            self.hsv_min_h = h0
            self.hsv_max_h = h1
            self.hsv_min_s = s0
            self.hsv_max_s = s1
            self.hsv_min_v = v0
            self.hsv_max_v = v1
            self.color_preset = preset

    def reset_hsv(self) -> None:
        """Сбрасывает текущие границы фильтрации HSV к значениям по умолчанию."""
        self.hsv_min_h = 0
        self.hsv_max_h = 179
        self.hsv_min_s = 0
        self.hsv_max_s = 255
        self.hsv_min_v = 0
        self.hsv_max_v = 255
        self.color_preset = "custom"


# Глобальный единственный экземпляр конфигурации
config = Config()