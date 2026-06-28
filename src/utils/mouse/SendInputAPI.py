"""Модуль низкоуровневой эмуляции ввода SendInput (Win32 API).

Обеспечивает прямое взаимодействие с операционной системой Windows для симуляции
перемещения указателя мыши, кликов и нажатий клавиш клавиатуры.
"""

import ctypes
from ctypes import wintypes

from . import state
from .keycodes import to_vk_code

# Константы Win32 API для SendInput
INPUT_MOUSE: int = 0
INPUT_KEYBOARD: int = 1
MOUSEEVENTF_MOVE: int = 0x0001
MOUSEEVENTF_LEFTDOWN: int = 0x0002
MOUSEEVENTF_LEFTUP: int = 0x0004
KEYEVENTF_KEYUP: int = 0x0002

# Динамическое определение разрядности указателя для x64/x86 архитектур
if ctypes.sizeof(ctypes.c_void_p) == 8:
    ULONG_PTR = ctypes.c_ulonglong
else:
    ULONG_PTR = ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    """Структура Win32 MOUSEINPUT для передачи событий мыши."""

    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    """Структура Win32 KEYBDINPUT для передачи событий клавиатуры."""

    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class _INPUTUNION(ctypes.Union):
    """Объединение (Union) для структур ввода в операционной системе Windows."""

    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    """Общая контейнерная структура INPUT, передаваемая в функцию SendInput."""

    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUTUNION),
    ]


# Загрузка системной библиотеки User32.dll с поддержкой отслеживания ошибок
_USER32 = ctypes.WinDLL("user32", use_last_error=True)


def _send_mouse(flags: int, dx: int = 0, dy: int = 0, data: int = 0) -> None:
    """Формирует и отправляет низкоуровневый пакет события мыши в Windows OS."""
    if not state.is_connected or state.active_backend != "SendInput":
        return

    mouse_input = MOUSEINPUT(
        dx=int(dx),
        dy=int(dy),
        mouseData=int(data),
        dwFlags=int(flags),
        time=0,
        dwExtraInfo=0,
    )
    packet = INPUT(type=INPUT_MOUSE, mi=mouse_input)

    sent = int(_USER32.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT)))
    if sent != 1:
        err = ctypes.get_last_error()
        if err:
            state.last_connect_error = f"SendInput failed (winerr={err})"


def _send_keyboard(vk_code: int, key_up: bool = False) -> None:
    """Формирует и отправляет низкоуровневый пакет события клавиатуры в Windows OS."""
    if not state.is_connected or state.active_backend != "SendInput":
        return

    key_input = KEYBDINPUT(
        wVk=int(vk_code),
        wScan=0,
        dwFlags=(KEYEVENTF_KEYUP if key_up else 0),
        time=0,
        dwExtraInfo=0,
    )
    packet = INPUT(type=INPUT_KEYBOARD, ki=key_input)

    sent = int(_USER32.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT)))
    if sent != 1:
        err = ctypes.get_last_error()
        if err:
            state.last_connect_error = f"SendInput keyboard failed (winerr={err})"


def move(x: float, y: float) -> None:
    """Выполняет относительное перемещение курсора мыши.

    Args:
        x: Смещение по горизонтали (dx).
        y: Смещение по вертикали (dy).
    """
    _send_mouse(MOUSEEVENTF_MOVE, dx=int(x), dy=int(y))


def move_bezier(x: float, y: float, segments: int, ctrl_x: float, ctrl_y: float) -> None:
    """Выполняет перемещение по траектории Безье (обёртка совместимости CVM).

    Args:
        x: Конечная точка смещения по X.
        y: Конечная точка смещения по Y.
        segments: Количество шагов интерполяции.
        ctrl_x: Контрольная точка кривизны X.
        ctrl_y: Контрольная точка кривизны Y.
    """
    _ = (segments, ctrl_x, ctrl_y)
    move(x, y)


def left(isdown: int) -> None:
    """Изменяет состояние нажатия левой кнопки мыши (LMB).

    Args:
        isdown: 1 для зажатия кнопки, 0 для её отпускания.
    """
    _send_mouse(MOUSEEVENTF_LEFTDOWN if isdown else MOUSEEVENTF_LEFTUP)


def key_down(key) -> None:
    """Выполняет виртуальное зажатие клавиши клавиатуры.

    Args:
        key: Название, токен или код клавиши для трансляции.
    """
    vk = to_vk_code(key)
    if vk is not None:
        _send_keyboard(vk, key_up=False)


def key_up(key) -> None:
    """Выполняет виртуальное отпускание клавиши клавиатуры.

    Args:
        key: Название, токен или код клавиши для трансляции.
    """
    vk = to_vk_code(key)
    if vk is not None:
        _send_keyboard(vk, key_up=True)


def is_key_pressed_win32(key) -> bool:
    """Проверяет физическое состояние клавиши в системе через GetAsyncKeyState.

    Args:
        key: Строковый токен или числовой код клавиши.

    Returns:
        bool: True, если клавиша зажата на клавиатуре в данный момент.
    """
    vk = to_vk_code(key)
    if vk is None:
        return False
    # Старший бит ответа GetAsyncKeyState указывает на текущее удержание клавиши
    return bool(_USER32.GetAsyncKeyState(int(vk)) & 0x8000)