"""
numbinder module: layout fixer (RU <-> EN) for the text in the active input field.

How it works:
  1. Select all text in the focused field (Ctrl+A).
  2. Copy it (Ctrl+C) and read the clipboard.
  3. Swap the layout of every letter (RU <-> EN).
  4. Paste the fixed text back (Ctrl+V). The selection is replaced.
  5. Put the old clipboard content back.

This is the built-in example module. See MODULES_GUIDE.txt.
"""
import time
import ctypes
import pyperclip

MODULE = {
    "id": "layout_fixer",
    "name": {"ru": "Layout fixer", "en": "Layout fixer"},
    "description": {
        "ru": "Берёт весь текст из активного поля, исправляет раскладку и вставляет обратно.",
        "en": "Takes all text from the active input field, fixes the keyboard layout and pastes it back.",
    },
    "version": "2.1.0",
    "author": "numbinder",
    "hold": True,   # второй режим: удержание кнопки — то же самое, но без Ctrl+A (берётся выделенный текст)
}

RU = """йцукенгшщзхъфывапролджэячсмитьбю.ЙЦУКЕНГШЩЗХЪФЫВАПРОЛДЖЭЯЧСМИТЬБЮ,ёЁ"№;%:?"""
EN = """qwertyuiop[]asdfghjkl;'zxcvbnm,./QWERTYUIOP{}ASDFGHJKL:"ZXCVBNM<>?`~@#$%^&"""
_RU_TO_EN = str.maketrans(RU, EN)
_EN_TO_RU = str.maketrans(EN, RU)

VK_CONTROL = 0x11
VK_A = 0x41
VK_C = 0x43
VK_V = 0x56
KEYUP = 0x0002


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


def _press_ctrl_key(vk):
    """Ctrl + <key>, sent as real keyboard events."""
    u32 = ctypes.windll.user32
    u32.keybd_event(VK_CONTROL, 0, 0, 0)
    time.sleep(0.02)
    u32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    u32.keybd_event(vk, 0, KEYUP, 0)
    time.sleep(0.02)
    u32.keybd_event(VK_CONTROL, 0, KEYUP, 0)


def _safe_paste():
    try:
        return pyperclip.paste()
    except Exception:
        return ""


def run(ctx, cfg):
    """Entry point. ctx: numbinder helpers (ctx.osd, ctx.log, ctx.settings). cfg: the button settings."""
    old_clip = _safe_paste()
    marker = f"__numbinder_marker_{time.time()}__"

    # 1-2. (click mode only) select all; then copy, wait for the clipboard to change
    hold = bool(getattr(ctx, "is_hold", False))
    pyperclip.copy(marker)
    time.sleep(0.05)
    if not hold:
        _press_ctrl_key(VK_A)
        time.sleep(0.05)
    _press_ctrl_key(VK_C)

    txt = marker
    deadline = time.time() + 0.8
    while time.time() < deadline:
        txt = _safe_paste()
        if txt != marker:
            break
        time.sleep(0.05)

    if not txt or txt == marker:
        pyperclip.copy(old_clip)
        ctx.osd("✗ Nothing to fix")
        return

    # 3. fix the layout
    new_txt = fix_layout(txt)
    if not new_txt:
        pyperclip.copy(old_clip)
        return

    # 4. paste over the selection (still selected from Ctrl+A)
    pyperclip.copy(new_txt)
    time.sleep(0.05)
    _press_ctrl_key(VK_V)
    ctx.osd(f"✓ {new_txt[:60]}")

    # 5. restore the clipboard after the paste has been handled
    time.sleep(0.4)
    pyperclip.copy(old_clip)
