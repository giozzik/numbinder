"""
numbinder module: layout fixer (RU <-> EN) for the clipboard text.
This is the built-in example module. See MODULES_GUIDE.txt.
"""
import time
import ctypes
import pyperclip

MODULE = {
    "id": "layout_fixer",
    "name": {"ru": "Layout fixer", "en": "Layout fixer"},
    "description": {
        "ru": "Takes the clipboard text, fixes the keyboard layout and pastes it back.",
        "en": "Takes the clipboard text, fixes the keyboard layout and pastes it back.",
    },
    "version": "1.0.0",
    "author": "numbinder",
}

RU = """йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,ёЁ"№;%:?"""
EN = """qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>?`~@#$%^&"""
_RU_TO_EN = str.maketrans(RU, EN)
_EN_TO_RU = str.maketrans(EN, RU)


def detect_layout(text):
    first = next((c for c in text if c.isalpha()), None)
    last = next((c for c in reversed(text) if c.isalpha()), None)
    if (first is not None and first in RU) or (last is not None and last in RU):
        return "ru"
    if (first is not None and first in EN) or (last is not None and last in EN):
        return "en"
    return None


def fix_layout(text):
    layout = detect_layout(text)
    if layout == "ru":
        return text.translate(_RU_TO_EN)
    if layout == "en":
        return text.translate(_EN_TO_RU)
    return ""


def _simulate_ctrl_v():
    ctypes.windll.user32.keybd_event(0x11, 0, 0, 0)
    time.sleep(0.02)
    ctypes.windll.user32.keybd_event(0x56, 0, 0, 0)
    time.sleep(0.02)
    ctypes.windll.user32.keybd_event(0x56, 0, 2, 0)
    time.sleep(0.02)
    ctypes.windll.user32.keybd_event(0x11, 0, 2, 0)


def run(ctx, cfg):
    """Entry point. ctx: numbinder helpers (ctx.osd, ctx.log, ctx.settings). cfg: the button settings."""
    txt = pyperclip.paste()
    if not txt:
        return
    new_txt = fix_layout(txt)
    if not new_txt:
        return
    ctx.osd(f"✓ {new_txt}")
    pyperclip.copy(new_txt)
    time.sleep(0.1)
    _simulate_ctrl_v()
