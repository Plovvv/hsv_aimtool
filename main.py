"""Главный модуль запуска приложения HSV Color Detector."""

import os
import sys

# Добавляем корневую директорию проекта в sys.path для корректных относительных импортов
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.ui_main import MainApp
from src.utils.logger import logger


def main() -> None:
    """Инициализирует логгер, создает главное окно и запускает цикл приложения."""
    logger.log("Запуск HSV Color Detector...", "INFO")
    app = MainApp()
    app.mainloop()


if __name__ == "__main__":
    main()
    