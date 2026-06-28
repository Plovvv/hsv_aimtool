"""Модуль трансляции и маппинга кодов клавиш.

Обеспечивает взаимную конвертацию между строковыми токенами, виртуальными кодами
клавиатуры Windows (VK) и аппаратными скан-кодами (HID) для CVM подсистем.
"""

import re

_DIGIT_TO_HID = {
    "1": 30,
    "2": 31,
    "3": 32,
    "4": 33,
    "5": 34,
    "6": 35,
    "7": 36,
    "8": 37,
    "9": 38,
    "0": 39,
}

_DIGIT_TO_VK = {
    "0": 0x30,
    "1": 0x31,
    "2": 0x32,
    "3": 0x33,
    "4": 0x34,
    "5": 0x35,
    "6": 0x36,
    "7": 0x37,
    "8": 0x38,
    "9": 0x39,
}


def _build_vk_by_name():
    """Строит карту соответствия строковых имен их Windows VK-кодам."""
    mapping = {
        "BACKSPACE": 0x08,
        "TAB": 0x09,
        "ENTER": 0x0D,
        "SHIFT": 0x10,
        "CONTROL": 0x11,
        "MENU": 0x12,  # Alt
        "PAUSE": 0x13,
        "CAPSLOCK": 0x14,
        "ESCAPE": 0x1B,
        "SPACE": 0x20,
        "PAGEUP": 0x21,
        "PAGEDOWN": 0x22,
        "END": 0x23,
        "HOME": 0x24,
        "LEFT": 0x25,
        "UP": 0x26,
        "RIGHT": 0x27,
        "DOWN": 0x28,
        "PRINTSCREEN": 0x2C,
        "INSERT": 0x2D,
        "DELETE": 0x2E,
        "LWIN": 0x5B,
        "RWIN": 0x5C,
        "APPS": 0x5D,
        "SLEEP": 0x5F,
        "NUMPAD0": 0x60,
        "NUMPAD1": 0x61,
        "NUMPAD2": 0x62,
        "NUMPAD3": 0x63,
        "NUMPAD4": 0x64,
        "NUMPAD5": 0x65,
        "NUMPAD6": 0x66,
        "NUMPAD7": 0x67,
        "NUMPAD8": 0x68,
        "NUMPAD9": 0x69,
        "MULTIPLY": 0x6A,
        "ADD": 0x6B,
        "SEPARATOR": 0x6C,
        "SUBTRACT": 0x6D,
        "DECIMAL": 0x6E,
        "DIVIDE": 0x6F,
        "F1": 0x70,
        "F2": 0x71,
        "F3": 0x72,
        "F4": 0x73,
        "F5": 0x74,
        "F6": 0x75,
        "F7": 0x76,
        "F8": 0x77,
        "F9": 0x78,
        "F10": 0x79,
        "F11": 0x7A,
        "F12": 0x7B,
        "NUMLOCK": 0x90,
        "SCROLLLOCK": 0x91,
        "LSHIFT": 0xA0,
        "RSHIFT": 0xA1,
        "LCONTROL": 0xA2,
        "RCONTROL": 0xA3,
        "LMENU": 0xA4,
        "RMENU": 0xA5,
    }
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        mapping[ch] = ord(ch)
    return mapping


def _build_hid_by_name():
    """Строит карту соответствия строковых имен их аппаратным HID-кодам."""
    mapping = {
        "ENTER": 40,
        "ESCAPE": 41,
        "BACKSPACE": 42,
        "TAB": 43,
        "SPACE": 44,
        "MINUS": 45,
        "EQUAL": 46,
        "LEFTBRACE": 47,
        "RIGHTBRACE": 48,
        "BACKSLASH": 49,
        "NONUSHASH": 50,
        "SEMICOLON": 51,
        "APOSTROPHE": 52,
        "GRAVE": 53,
        "COMMA": 54,
        "DOT": 55,
        "SLASH": 56,
        "CAPSLOCK": 57,
        "F1": 58,
        "F2": 59,
        "F3": 60,
        "F4": 61,
        "F5": 62,
        "F6": 63,
        "F7": 64,
        "F8": 65,
        "F9": 66,
        "F10": 67,
        "F11": 68,
        "F12": 69,
        "PRINTSCREEN": 70,
        "SCROLLLOCK": 71,
        "PAUSE": 72,
        "INSERT": 73,
        "HOME": 74,
        "PAGEUP": 75,
        "DELETE": 76,
        "END": 77,
        "PAGEDOWN": 78,
        "RIGHT": 79,
        "LEFT": 80,
        "DOWN": 81,
        "UP": 82,
        "NUMLOCK": 83,
        "KPMULTIPLY": 85,
        "KPMINUS": 86,
        "KPPLUS": 87,
        "KPENTER": 88,
        "KP1": 89,
        "KP2": 90,
        "KP3": 91,
        "KP4": 92,
        "KP5": 93,
        "KP6": 94,
        "KP7": 95,
        "KP8": 96,
        "KP9": 97,
        "KP0": 98,
        "KPDOT": 99,
        "NONUSBACKSLASH": 100,
        "APPLICATION": 101,
        "LCTRL": 224,
        "LSHIFT": 225,
        "LALT": 226,
        "LGUI": 227,
        "RCTRL": 228,
        "RSHIFT": 229,
        "RALT": 230,
        "RGUI": 231,
    }
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        idx = ord(ch) - ord("A")
        mapping[ch] = 4 + idx
    return mapping


_VK_BY_NAME = _build_vk_by_name()
_HID_BY_NAME = _build_hid_by_name()

_ALIASES = {
    "ctrl": "CONTROL",
    "lctrl": "LCONTROL",
    "rctrl": "RCONTROL",
    "alt": "MENU",
    "lalt": "LMENU",
    "ralt": "RMENU",
    "win": "LWIN",
    "cmd": "LWIN",
    "esc": "ESCAPE",
    "spacebar": "SPACE",
    "caps": "CAPSLOCK",
    "scroll": "SCROLLLOCK",
    "num": "NUMLOCK",
    "back": "BACKSPACE",
    "del": "DELETE",
    "ins": "INSERT",
    "pgup": "PAGEUP",
    "pgdn": "PAGEDOWN",
}

_ALIASES_HID = {
    "control": "LCTRL",
    "ctrl": "LCTRL",
    "rctrl": "RCTRL",
    "shift": "LSHIFT",
    "alt": "LALT",
    "menu": "LALT",
    "win": "LGUI",
    "lwin": "LGUI",
    "rwin": "RGUI",
}


def _vk_to_hid(vk: int):
    """Внутренний маппинг некоторых VK-кодов Windows в аппаратные скан-коды HID."""
    if 0x41 <= vk <= 0x5A:
        return 4 + (vk - 0x41)
    if 0x31 <= vk <= 0x39:
        return 30 + (vk - 0x31)
    if vk == 0x30:
        return 39
    m = {
        0x0D: 40,   # ENTER
        0x1B: 41,   # ESC
        0x08: 42,   # BACKSPACE
        0x09: 43,   # TAB
        0x20: 44,   # SPACE
        0x25: 80,   # LEFT
        0x26: 82,   # UP
        0x27: 79,   # RIGHT
        0x28: 81,   # DOWN
        0xA0: 225,  # LSHIFT
        0x10: 225,  # SHIFT -> LSHIFT
        0xA1: 229,  # RSHIFT
        0xA2: 224,  # LCONTROL
        0x11: 224,  # CTRL -> LCTRL
        0xA3: 228,  # RCONTROL
        0xA4: 226,  # LMENU (LALT)
        0x12: 226,  # ALT -> LALT
        0xA5: 230,  # RMENU
    }
    return m.get(vk)


def _safe_int(value):
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _strip_prefix(value: str):
    s = value.strip()
    m = re.match(r"^([A-Za-z0-9]+)[:_-](.+)$", s)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    return None, s


def _normalize_name(name: str):
    s = name.strip().upper()
    s = re.sub(r"\s+", "", s)
    return s if s else None


def _parse_int_text(text: str):
    s = text.strip()
    if s.lower().startswith("0x"):
        try:
            return int(s, 16)
        except ValueError:
            return None
    if s.isdigit():
        return int(s)
    return None


def to_vk_code(value) -> int:
    """Преобразует переданный идентификатор в виртуальный код клавиши Windows (VK).

    Args:
        value: Число, строка с префиксом или имя клавиши.

    Returns:
        int: VK-код клавиши или None, если символ не распознан.
    """
    if value is None:
        return None
    direct = _safe_int(value)
    if direct is not None:
        return int(direct)

    prefix, body = _strip_prefix(value)
    if not body:
        return None

    if prefix == "HID":
        return None

    numeric = _parse_int_text(body)
    if numeric is not None:
        return int(numeric)

    token = _normalize_name(body)
    if token is None:
        return None

    if token in _DIGIT_TO_VK:
        return _DIGIT_TO_VK[token]

    token = _ALIASES.get(token, token)
    return _VK_BY_NAME.get(token)


def to_hid_code(value) -> int:
    """Преобразует переданный идентификатор в аппаратный скан-код (HID).

    Args:
        value: Число, строка с префиксом или имя клавиши.

    Returns:
        int: Аппаратный HID скан-код или None.
    """
    if value is None:
        return None
    direct = _safe_int(value)
    if direct is not None:
        return int(direct)

    prefix, body = _strip_prefix(value)
    if not body:
        return None

    if prefix == "VK":
        vk = to_vk_code(body)
        return _vk_to_hid(vk)

    numeric = _parse_int_text(body)
    if numeric is not None:
        return int(numeric)

    token = _normalize_name(body)
    if token is None:
        return None

    token = _ALIASES.get(token, token)
    token = _ALIASES_HID.get(token, token)
    hid = _HID_BY_NAME.get(token)
    if hid is not None:
        return hid

    vk = _VK_BY_NAME.get(token)
    if vk is not None:
        return _vk_to_hid(vk)

    return None


def to_key_token(value) -> str:
    """Приводит переданное значение к строковому представлению токена.

    Args:
        value: Входной идентификатор клавиши.

    Returns:
        str: Строковый токен кода клавиши.
    """
    if value is None:
        return None
    numeric = _safe_int(value)
    if numeric is not None:
        return str(int(numeric))

    prefix, body = _strip_prefix(value)
    if not body:
        return None

    if prefix == "VK":
        vk = to_vk_code(body)
        if vk is None:
            return None
        return str(int(vk))
    if prefix == "HID":
        hid = to_hid_code(body)
        if hid is None:
            return None
        return str(int(hid))

    numeric_text = _parse_int_text(body)
    if numeric_text is not None:
        return str(int(numeric_text))

    token = _normalize_name(body)
    if token is None:
        return None

    token_alias = _ALIASES.get(token, token)
    if token_alias in _VK_BY_NAME:
        return str(int(_VK_BY_NAME[token_alias]))

    if token in _DIGIT_TO_VK:
        return str(int(_DIGIT_TO_VK[token]))

    return str(body)