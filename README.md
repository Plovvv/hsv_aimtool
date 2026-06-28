# HSV Color Detector

Инструмент разработчика игр для настройки и отладки HSV-детекции объектов в реальном времени.

## Что делает

- Захватывает область экрана вокруг центра (настраиваемый FOV)
- Применяет HSV-фильтр и находит объекты по цвету
- Показывает оверлей с bounding box и маской в реальном времени
- Позволяет настраивать HSV-диапазоны через слайдеры
- Сохраняет/загружает профили настроек в JSON
- Ведёт лог событий с окном отладки

## Как запустить

```bash
pip install -r requirements.txt
python main.py
```

## Структура проекта

```
hsv_aimtool/
├── main.py                  # Точка входа
├── requirements.txt
├── config.json              # Сохранённые настройки (создаётся автоматически)
└── src/
    ├── ui_main.py           # Главный UI (MainApp, NeonFrame, HSVSliderRow, GlowLabel)
    ├── core/
    │   └── detector.py      # HSVDetector, DetectedObject, DetectionResult
    └── utils/
        ├── config.py        # Config, COLOR_PRESETS
        └── logger.py        # DebugLogger
```

## Вкладки

| Вкладка   | Описание |
|-----------|----------|
| General   | FOV, FPS, настройки визуализации, пресеты цветов |
| HSV Range | Слайдеры H/S/V с live-превью цвета |
| Preview   | Живой оверлей и бинарная маска детекции |
| Debug     | Статистика FPS/ms, текущий HSV, лог событий |

## Требования

- Python 3.10+
- Windows / Linux / macOS
