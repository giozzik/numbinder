import sys
import traceback
import ctypes
import os
import datetime as _dt
import atexit
import threading as _th

# ---- Лог на каждый запуск: C:\numbinder\crashlogs\run_<дата>_pid<N>.txt ----
BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # папка, в которой лежит numbinder.pyw
PATH_CRASH_DIR = os.path.join(BASE_DIR, "crashlogs")
try:
    os.makedirs(PATH_CRASH_DIR, exist_ok=True)
except Exception:
    pass
RUN_LOG = os.path.join(PATH_CRASH_DIR, "run_" + _dt.datetime.now().strftime("%Y-%m-%d_%H-%M-%S") + f"_pid{os.getpid()}.txt")

def _runlog(text):
    try:
        with open(RUN_LOG, "a", encoding="utf-8") as f:
            f.write(str(text).rstrip("\n") + "\n")
    except Exception:
        pass

_runlog(f"START {_dt.datetime.now().isoformat()} argv={sys.argv} exe={sys.executable}")
atexit.register(lambda: _runlog(f"EXIT {_dt.datetime.now().isoformat()}"))

def _thread_hook(args):
    _runlog("THREAD ERROR in " + str(getattr(args.thread, 'name', '?')) + ":\n" +
            "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
_th.excepthook = _thread_hook

# ================= АБСОЛЮТНЫЙ КРАШ-РЕПОРТЕР =================
def _crash_lang():
    try:
        with open(os.path.join(BASE_DIR, "config.json"), "r", encoding="utf-8") as _f:
            return "en"
    except Exception:
        return "en"

def _crash_text(ru, en):
    return en if _crash_lang() == "en" else ru

def global_exception_handler(exc_type, exc_value, exc_traceback):
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    _runlog("UNHANDLED:\n" + tb_text)
    ctypes.windll.user32.MessageBoxW(0, _crash_text("Critical startup error!", "Critical startup error!") + f"\n\n{tb_text}", "numbinder Crash", 0x10 | 0x40000)
    sys.exit(1)

sys.excepthook = global_exception_handler

class CrashStream:
    def write(self, data):
        if data.strip():
            try:
                _runlog(data)
            except: pass
    def flush(self): pass

if sys.stdout is None: sys.stdout = CrashStream()
if sys.stderr is None: sys.stderr = CrashStream()
# ============================================================

def tr(s):  # placeholder until config is loaded; real tr() is defined below
    return s

print("Starting numbinder...")

import threading
import time
import queue
import json
import os
import re
import base64
import webbrowser
import collections

# Windows timers tick every 15.6 ms by default, so Tk's after(16) really waits ~31 ms (~30 fps).
# 1 ms resolution lets animations run at a real ~60 fps.
try:
    ctypes.windll.winmm.timeBeginPeriod(1)
    atexit.register(lambda: ctypes.windll.winmm.timeEndPeriod(1))
except Exception:
    pass

try:
    import psutil
    from ctypes import wintypes
    import comtypes
    import subprocess
    import pyperclip
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
    import pystray
    from pystray import MenuItem as item
    from pycaw.pycaw import AudioUtilities, ISimpleAudioVolume
    from PIL import Image, ImageTk, ImageDraw, ImageOps, ImageFilter, ImageFont, ImageChops

    print("Libraries loaded.")
    _runlog("libs loaded")

    # Одна копия за раз: именованный mutex Windows вместо убийства других процессов.
    # (Прежний код убивал любой python с тем же путём, в том числе родительский процесс.)
    _single_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "numbinder_single_instance")
    if ctypes.windll.kernel32.GetLastError() == 183 and "--after-update" in sys.argv:
        for _ in range(80):   # после обновления ждём, пока завершится старая копия
            time.sleep(0.25)
            _single_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "numbinder_single_instance")
            if ctypes.windll.kernel32.GetLastError() != 183: break
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        _runlog("another numbinder instance is already running -> exit 0")
        ctypes.windll.user32.MessageBoxW(0, _crash_text("numbinder is already running.", "numbinder is already running."), "numbinder", 0x40)
        sys.exit(0)

    # ================= НАСТРОЙКИ =================
    VERSION = "v1.36.0"
    BUILD = 20                    # номер сборки: растёт на 1 при каждом релизе
    GH_REPO = "giozzik/numbinder"
    CHANGELOG = [
        ("v1.36.0", ["New button type: Microphone mute. Mutes the default mic in all apps at once.",
                     "Modes: toggle (press), push to talk (hold), push to mute (hold)."]),
        ("v1.35.0", ["Smoother interface: animations run at ~60 fps (1 ms Windows timer).",
                     "Hover animation uses cached frames instead of re-blurring the glow every frame.",
                     "Animation speed no longer depends on frame rate; mouse moves are coalesced."]),
        ("v1.34.1", ["Fixed: the Enable anyway button was cut off in the Extended keyboard warning."]),
        ("v1.34.0", ["Experimental: Extended keyboard (Settings → Experimental). Bind F-keys, arrows, Insert…Page Down, Right Alt and Right Ctrl.",
                     "With it on, the main window grows to the left and shows a red warning plate."]),
        ("v1.33.2", ["Numpad Enter can now be used as a button, like the other numpad keys."]),
        ("v1.33.1", ["Fixed: Launch app opened the numbinder folder when no path was set.",
                     "The app path is filled in from the picked app; a missing path shows a message."]),
        ("v1.33.0", ["Launch\\Close app: several actions per button (hold N sec or press N times).",
                     "Hold: the hold time closest to yours runs on release. Multiple hold times supported.",
                     "New actions: Launch app, Close process, Restart app, Minimize to tray.",
                     "Old settings are converted automatically."]),
        ("v1.32.3", ["Fixed: the window no longer jitters left and right while dragging.",
                     "Fixed the same jitter when dragging an overlay."]),
        ("v1.32.2", ["One app picker for exec, volume and clean2;0 keep-open list.",
                     "Picker shows app names and icons; apps that are not running come from the Start menu."]),
        ("v1.32.1", ["Start with Windows: Task Scheduler task without the 72-hour limit, errors are shown.",
                     "Start with Windows: second way via the Startup folder, see \"other ways\"."]),
        ("v1.32.0", ["New button type: Media control (play/pause, next, previous, stop, mute).",
                     "Type descriptions fit the panel width."]),
        ("v1.31.9", ["Settings: buttons no longer squeezed, Back moved to the top.",
                     "Settings: Go to GitHub page button.",
                     "clean2;0: Keep open list for apps that must not be closed.",
                     "Pair Button no longer offers NumLock or numpad /.",
                     "Each button type has a short description under the Back / Save row.",
                     "Crosshair: designer button and an overlay hint in the button settings."]),
        ("v1.31.8", ["Interface is English only.", "Square reset icons for the colour settings.", "This changelog window."]),
        ("v1.31.7", ["Button colour is applied right after saving, no restart.", "Button settings window slides down from the top.",
                     "Reset button for button colours, new default hover values.", "Clipboard patch system removed.",
                     "clean2;0: hold to close extra apps (system apps are never touched).",
                     "Layout fixer: hold mode fixes the selected text without Ctrl+A."]),
        ("v1.31.6", ["Hover offset 3 px, tilt and glow tuned.", "Button press animation: shrinks and bounces back.",
                     "Button settings window slides up from the bottom.", "Reset icon for the icon colour."]),
        ("v1.31.5", ["Buttons move away from the cursor and tilt instead of a copy drawn on top.",
                     "Click area matches the sprite.", "No flicker at the edge of a button."]),
        ("v1.31.4", ["Volume button: Points mode (cycle through set levels).", "Friendly names for button types.",
                     "Glow colour in global settings, dimming on hover removed.", "Layout fixer works on the whole field."]),
        ("v1.31.3", ["Paired volume buttons stay in sync in both directions.", "Each button shows its pair."]),
        ("v1.31.2", ["Faster hover, cursor no longer flickers.", "Settings window appears fully drawn."]),
    ]   # показывается после обновления и по кнопке «What's new» в настройках
    VOLUME_LIMIT = 0.65 
    macro_enabled = True 
    active_keys = {}
    osd_queue = queue.Queue()
    vol_dir = 0
    vol_target = ""
    vol_mode = "process"
    vol_thread = None
    secret_buffer = ""

    PATH_DIR = BASE_DIR
    WIN_W, WIN_H = 444, 704   # размер окна фиксированный
    script_path = os.path.abspath(__file__)
    # Все картинки и звук лежат в C:\numbinder\assets\. Старое расположение (корень папки) тоже поддерживается.
    PATH_ASSETS = os.path.join(PATH_DIR, "assets")
    def asset(rel):
        """All images and sounds are loaded ONLY from the assets folder next to numbinder.pyw."""
        return os.path.join(PATH_ASSETS, rel)
    _resolved_warned = set()
    def resolve_icon(p):
        """Если путь из настроек кнопки не существует, берём файл с тем же именем из assets\\."""
        if not p or p == "-1" or os.path.exists(p): return p
        cand = asset(os.path.basename(p))
        if os.path.exists(cand): return cand
        if p not in _resolved_warned:
            _resolved_warned.add(p)
            _runlog(f"ICON NOT FOUND: {p} (and no {cand})")
        return p
    PATH_LOGO = asset("logo.png")
    PATH_CONFIG = os.path.join(PATH_DIR, "config.json")
    
    PATH_BP = ""
    for ext in ["png", "jpg", "jpeg"]:
        p = asset(f"bp.{ext}")
        if os.path.exists(p):
            PATH_BP = p
            break
    
    PATH_BTN_SINGLE = asset(r"numpad\single.png")
    PATH_BTN_HOR = asset(r"numpad\double_hor.png")
    PATH_BTN_VERT = asset(r"numpad\double_vert.png")

    def _report_assets():
        from PIL import Image as _I
        _runlog(f"ASSETS DIR: {PATH_ASSETS} exists={os.path.isdir(PATH_ASSETS)}")
        try:
            _runlog("ASSETS CONTENT: " + ", ".join(sorted(os.listdir(PATH_ASSETS))))
        except Exception as e:
            _runlog(f"ASSETS CONTENT: {e}")
        for label, pth in [("logo", PATH_LOGO), ("btn single", PATH_BTN_SINGLE), ("btn hor", PATH_BTN_HOR), ("btn vert", PATH_BTN_VERT)]:
            if not os.path.exists(pth):
                _runlog(f"ASSET MISSING {label}: {pth}")
                continue
            try:
                im = _I.open(pth); im.load()
                _runlog(f"ASSET OK {label}: {pth} {im.size} {im.mode}")
            except Exception as e:
                _runlog(f"ASSET BROKEN {label}: {pth} -> {e}")
    _report_assets()

    SC_NAMES = {
        "69": "NUMLK", "53": "/", "55": "*", "74": "-",
        "71": "7", "72": "8", "73": "9", "78": "+",
        "75": "4", "76": "5", "77": "6",
        "79": "1", "80": "2", "81": "3", "284": "ENT",
        "82": "0", "83": ".",
        # extended keyboard (experimental): F-row, Ins..PgDn, arrows, RAlt, RCtrl
        "59": "F1", "60": "F2", "61": "F3", "62": "F4", "63": "F5", "64": "F6",
        "65": "F7", "66": "F8", "67": "F9", "68": "F10", "87": "F11", "88": "F12",
        "338": "INS", "327": "HOME", "329": "PGUP", "339": "DEL", "335": "END", "337": "PGDN",
        "328": "↑", "331": "←", "336": "↓", "333": "→", "312": "RALT", "285": "RCTRL",
    }

    MACRO_TEMPLATE = {
        "Type": "none", "Language": "-1", "Path": "-1", "ProcessName": "-1", 
        "ActionTime": 0, "SecondActionTime": -1, "AdminRights": -1, "VolumeDirection": 1, "Desc": tr("New macro"),
        "IconPath": "", "IconColor": "#ffffff",
        "Audio": {"limit": 65, "low_thresh": 15, "low_step": 1, "low_delay": 150, "mid_thresh": 50, "mid_step": 5, "mid_delay": 120, "high_step": 3, "high_delay": 100},
        "Overlay": {"path": "", "x": -1, "y": -1, "w": 200, "h": 200, "alpha": 80, "lock_aspect": True, "interactive": True, "smooth": True, "fix_alpha": False, "blend": "black"},
        "Crosshair": {"mode": "toggle", "name": "Default", "list": []},
        "Hotkey": []
    }

    DEFAULT_CONFIG = {
        "_version": VERSION,
        "AppSettings": {"show_labels": True, "autostart": False, "dev_unlocked": False, "dev_enabled": False, "osd_scale": 1.0, "osd_x": 50, "osd_y": 5, "action_sound": True, "action_sound_volume": 100, "osd_text_color": "#cccccc", "osd_border_color": "#c7c7c7", "osd_bg_color": "#202020", "osd_glow_color": "#ebebeb", "lang": "en", "auto_update": False, "update_remind_base": BUILD},
        "DevSettings": {
            "scale": 1.07, "base_size": 100, "spacing": 92, 
            "color_active": "#1db954", "color_inactive": "#3a3a3a",
            "text_x": 32, "text_y": 23, "text_size": 12,
            "text_x_nlk": 28, "text_y_nlk": 29, "text_size_nlk": 8,
            "text_x_ent": 33, "text_y_ent": 29, "text_size_ent": 12,
            "layout_defaults_rev": 2,
            "hover_scale": 1.32, "hover_y": 3, "hover_rev": 2, "hover_tilt": 3, "color_glow": "#1db954",
            "win_w": 444, "win_h": 704, "win_pad": 12, "hover_blur": 22,
            
            "theme_grad_top": "#2a2a2a", "theme_grad_bot": "#202020",
            "corner_style": 2, "window_alpha_pct": 100
        },
        "Crosshairs": {
            "Default": {
                "shape": "cross", "center_dot": True, "dot_size": 3,
                "line_length": 10, "line_thickness": 2, "gap": 4, "rotation": 0,
                "color": "#1db954", "opacity": 100,
                "outline_enabled": True, "outline_thickness": 1,
                "outline_color": "#000000", "outline_opacity": 100
            }
        },
        "80": {"Type": "Layout Fixer", "Language": "-1", "Path": "-1", "ProcessName": "-1", "ActionTime": 0, "SecondActionTime": -1, "AdminRights": -1, "VolumeDirection": 1, "Desc": "Layout Fixer (NUM 2)"}
    }

    # ================= UI ИНИЦИАЛИЗАЦИЯ =================
    try: ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except:
        try: ctypes.windll.user32.SetProcessDPIAware()
        except: pass

    ui_root = tk.Tk()
    ui_root.title(f"numbinder {VERSION}")
    ui_root.overrideredirect(True) 
    ui_root.withdraw()

    # Универсальный обработчик скролла
    def _on_global_mousewheel(event):
        try:
            widget = ui_root.winfo_containing(event.x_root, event.y_root)
        except KeyError:
            # Combobox dropdown ('popdown') can't be resolved by winfo_containing on some Tk builds
            return
        if not widget: return
        for _ in range(20):
            if isinstance(widget, tk.Canvas):
                # Наши собственные Canvas-виджеты (слайдер, переключатель) —
                # не настоящий скролл-контейнер, пропускаем их и идём выше.
                if getattr(widget, "not_scrollable", False):
                    widget = widget.master
                    if not widget: break
                    continue
                if getattr(widget, "is_main_canvas", False): break
                widget.yview_scroll(int(-1*(event.delta/120)), "units")
                break
            widget = widget.master
            if not widget: break

    ui_root.bind_all("<MouseWheel>", _on_global_mousewheel)

    def tk_crash_handler(exc, val, tb):
        tb_text = "".join(traceback.format_exception(exc, val, tb))
        try:
            _runlog("TK CRASH:\n" + tb_text)
        except: pass
        ctypes.windll.user32.MessageBoxW(0, tr("Animation or Tkinter failure!\n\nError: {}\n\nSee the crashlogs folder.").format(val), "Tkinter Crash", 0x10 | 0x40000)
        sys.exit(1)
    ui_root.report_callback_exception = tk_crash_handler

    try:
        myappid = 'numbinder.app.1'
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        icon_img = ImageTk.PhotoImage(Image.open(PATH_LOGO))
        ui_root.iconphoto(True, icon_img)
    except: pass

    if not os.path.exists(PATH_CONFIG):
        os.makedirs(os.path.dirname(PATH_CONFIG), exist_ok=True)
        with open(PATH_CONFIG, "w", encoding="utf-8") as f: json.dump(DEFAULT_CONFIG, f, indent=4, ensure_ascii=False)
        MACRO_CONFIG = DEFAULT_CONFIG.copy()
    else:
        try:
            with open(PATH_CONFIG, "r", encoding="utf-8") as f: MACRO_CONFIG = json.load(f)
        except: MACRO_CONFIG = DEFAULT_CONFIG.copy()

    if "AppSettings" not in MACRO_CONFIG: MACRO_CONFIG["AppSettings"] = DEFAULT_CONFIG["AppSettings"].copy()
    if "DevSettings" not in MACRO_CONFIG: MACRO_CONFIG["DevSettings"] = DEFAULT_CONFIG["DevSettings"].copy()
    if "Crosshairs" not in MACRO_CONFIG: MACRO_CONFIG["Crosshairs"] = {k: dict(v) for k, v in DEFAULT_CONFIG["Crosshairs"].items()}
    for k, v in DEFAULT_CONFIG["AppSettings"].items():
        if k not in MACRO_CONFIG["AppSettings"]: MACRO_CONFIG["AppSettings"][k] = v
    for k, v in DEFAULT_CONFIG["DevSettings"].items():
        if k not in MACRO_CONFIG["DevSettings"]: MACRO_CONFIG["DevSettings"][k] = v
    # Новые дефолтные значения сетки/текста применяются один раз к уже существующему config.json
    _LAYOUT_KEYS = ("scale", "base_size", "spacing", "text_x", "text_y", "text_size",
                    "text_x_nlk", "text_y_nlk", "text_size_nlk", "text_x_ent", "text_y_ent", "text_size_ent")
    if MACRO_CONFIG["DevSettings"].get("hover_rev", 0) < 2:
        # новые стоковые значения эффектов наведения
        MACRO_CONFIG["DevSettings"].update({"hover_scale": 1.32, "hover_y": 3, "hover_tilt": 3, "hover_blur": 22, "hover_rev": 2})
    if MACRO_CONFIG["DevSettings"].get("layout_defaults_rev", 0) < DEFAULT_CONFIG["DevSettings"]["layout_defaults_rev"]:
        for _k in _LAYOUT_KEYS:
            MACRO_CONFIG["DevSettings"][_k] = DEFAULT_CONFIG["DevSettings"][_k]
        MACRO_CONFIG["DevSettings"]["layout_defaults_rev"] = DEFAULT_CONFIG["DevSettings"]["layout_defaults_rev"]
        try:
            with open(PATH_CONFIG, "w", encoding="utf-8") as _f:
                json.dump(MACRO_CONFIG, _f, indent=4, ensure_ascii=False)
        except Exception:
            pass

    def tr(s):
        return s
        
    for k, v in list(MACRO_CONFIG.items()):
        if k.isdigit() and isinstance(v, dict):
            if "Overlay" not in v:
                v["Overlay"] = MACRO_TEMPLATE["Overlay"].copy()
            if "Crosshair" not in v:
                v["Crosshair"] = {"mode": "toggle", "name": "Default", "list": []}
            if "Hotkey" not in v:
                v["Hotkey"] = []

    MACRO_CONFIG["AppSettings"]["lang"] = "en"
    _OLD_DEF = "\u041f\u043e \u0443\u043c\u043e\u043b\u0447\u0430\u043d\u0438\u044e"   # старое русское имя прицела
    _cr = MACRO_CONFIG.get("Crosshairs", {})
    if _OLD_DEF in _cr:
        if "Default" not in _cr: _cr["Default"] = _cr[_OLD_DEF]
        del _cr[_OLD_DEF]
    for _k, _v in list(MACRO_CONFIG.items()):
        if _k.isdigit() and isinstance(_v, dict) and isinstance(_v.get("Crosshair"), dict):
            if _v["Crosshair"].get("name") == _OLD_DEF: _v["Crosshair"]["name"] = "Default"

    if MACRO_CONFIG.get("_version") != VERSION:
        MACRO_CONFIG["_version"] = VERSION
        with open(PATH_CONFIG, "w", encoding="utf-8") as f: json.dump(MACRO_CONFIG, f, indent=4, ensure_ascii=False)

    # ================= МОДУЛИ =================
    MODULES_DIR = os.path.join(PATH_DIR, "modules")
    MODULES = {}  # id -> {"info": dict, "run": callable, "file": str}

    def _L(ru, en):
        return en

    def _mod_name(info):
        n = info.get("name", info.get("id", "?"))
        if isinstance(n, dict):
            return n.get(MACRO_CONFIG["AppSettings"].get("lang", "ru"), n.get("ru", info.get("id", "?")))
        return str(n)

    TYPE_DESCRIPTIONS = {
        "none": "No action. The button is only a placeholder.",
        "exec": "Launches or closes an app. Add several actions: press once, press N times in a row, or hold for N seconds.",
        "lang": "Switches the keyboard layout to the next one in the language list.",
        "volume": "Changes the volume of an app or the system. Use Pair Button to link an up and a down button.",
        "restart": "Restarts numbinder.",
        "overlay": "Short press toggles the overlay. Hold opens the overlay studio.",
        "crosshair": "Shows or hides a crosshair on screen. Crosshairs are made in the crosshair designer.",
        "light macro": "Presses the key combination (hotkey) you record.",
        "clean": "clean2;0: on hold, closes your running apps. Use Keep open to list apps that must stay open.",
        "media": "Presses a media key: play/pause, next or previous track, stop or mute. Works with any player.",
        "mic": "Mutes your default microphone in all apps at once (Discord, games, calls). Toggle, push to talk or push to mute.",
    }
    # (config key, label, Windows virtual-key code)
    MEDIA_KEYS = [("playpause", "Play / Pause", 0xB3), ("next", "Next track", 0xB0),
                  ("prev", "Previous track", 0xB1), ("stop", "Stop", 0xB2), ("mute", "Mute", 0xAD)]

    def type_description(t):
        if t and t.startswith("mod:"):
            info = MODULES.get(t[4:], {}).get("info", {})
            d = info.get("description", "")
            return d.get("en", "") if isinstance(d, dict) else str(d or "")
        return TYPE_DESCRIPTIONS.get(t, "")

    def _type_labels():
        """Friendly button type names (config keys stay the same)."""
        return {
            "none": _L("None", "None"),
            "exec": _L("Launch\\Close app", "Launch\\Close app"),
            "lang": _L("Switch layout", "Switch layout"),
            "volume": _L("Volume", "Volume"),
            "restart": _L("Restart numbinder", "Restart numbinder"),
            "overlay": _L("Overlay", "Overlay"),
            "crosshair": _L("Crosshair", "Crosshair"),
            "light macro": _L("Simple macro", "Simple macro"),
            "clean": _L("clean2;0 — close extra processes", "clean2;0 — close extra processes"),
            "media": _L("Media control", "Media control"),
            "mic": _L("Microphone mute", "Microphone mute"),
        }

    def type_to_label(t):
        if isinstance(t, str) and t.startswith("mod:"):
            m = MODULES.get(t[4:])
            return ("🧩 " + _mod_name(m["info"])) if m else t
        return _type_labels().get(t, t)

    def label_to_type(l):
        if isinstance(l, str) and l.startswith("🧩 "):
            for mid, m in MODULES.items():
                if "🧩 " + _mod_name(m["info"]) == l: return "mod:" + mid
        for k, v in _type_labels().items():
            if v == l: return k
        return l

    def type_options():
        base = list(_type_labels().values())
        return base + [type_to_label("mod:" + mid) for mid in MODULES]

    def _load_modules():
        import importlib.util
        MODULES.clear()
        try: os.makedirs(MODULES_DIR, exist_ok=True)
        except Exception: pass
        try: names = sorted(os.listdir(MODULES_DIR))
        except Exception: names = []
        for fn in names:
            if not fn.endswith(".py") or fn.startswith("_"): continue
            try:
                spec = importlib.util.spec_from_file_location("nbmod_" + fn[:-3], os.path.join(MODULES_DIR, fn))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                info = getattr(mod, "MODULE", None)
                if not isinstance(info, dict) or not info.get("id") or not callable(getattr(mod, "run", None)):
                    raise ValueError("module has no MODULE['id'] or run(ctx, cfg) function")
                MODULES[str(info["id"])] = {"info": info, "run": mod.run, "file": fn}
            except Exception:
                _runlog(f"MODULE LOAD FAILED {fn}:\n" + traceback.format_exc())
        # старая кнопка «Layout Fixer» -> модуль layout_fixer
        for k, v in MACRO_CONFIG.items():
            if k.isdigit() and isinstance(v, dict) and v.get("Type") == "Layout Fixer":
                v["Type"] = "mod:layout_fixer"
        _runlog("modules loaded: " + ", ".join(MODULES.keys()))

    class ModuleContext:
        """What a module sees: helpers without access to numbinder internals."""
        def __init__(self, mod_id):
            self.module_id = mod_id
            self.is_hold = False   # True, если модуль запущен удержанием (только для модулей с "hold": True)
        def osd(self, text):
            show_osd(str(text))
        def log(self, text):
            _runlog(f"[module {self.module_id}] {text}")
        def settings(self):
            return MACRO_CONFIG.setdefault("Modules", {}).setdefault(self.module_id, {})
        def save_settings(self):
            save_config()

    _load_modules()

    # ================= АВТООБНОВЛЕНИЕ (GitHub Releases) =================
    def _http_get(url, timeout=15):
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "numbinder-updater", "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()

    def fetch_latest_release():
        """Returns {build, version, sha256, url} for the latest release, or None."""
        try:
            rel = json.loads(_http_get(f"https://api.github.com/repos/{GH_REPO}/releases/latest").decode("utf-8"))
            assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
            if "version.json" not in assets or "numbinder.pyw" not in assets:
                return None
            meta = json.loads(_http_get(assets["version.json"]).decode("utf-8"))
            return {"build": int(meta["build"]), "version": meta.get("version", rel.get("tag_name", "")),
                    "sha256": str(meta.get("sha256", "")).lower(), "url": assets["numbinder.pyw"]}
        except Exception as e:
            _runlog(f"update check failed: {e}")
            return None

    def _prune_backups(bdir, keep=10):
        try:
            files = sorted((os.path.join(bdir, f) for f in os.listdir(bdir) if f.startswith("numbinder_v")),
                           key=os.path.getmtime, reverse=True)
            for old in files[keep:]:
                os.remove(old)
        except Exception:
            pass

    def apply_update(info):
        """Downloads the new numbinder.pyw, verifies it, backs up the current one and restarts the program."""
        import hashlib, shutil, subprocess
        data = _http_get(info["url"], timeout=60)
        if info["sha256"] and hashlib.sha256(data).hexdigest() != info["sha256"]:
            raise ValueError("checksum mismatch")
        if len(data) < 5000:
            raise ValueError("downloaded file is too small")
        compile(data.decode("utf-8"), "numbinder.pyw", "exec")   # синтаксис проверяем до замены
        bdir = os.path.join(BASE_DIR, "backups")
        os.makedirs(bdir, exist_ok=True)
        shutil.copy2(script_path, os.path.join(bdir, f"numbinder_{VERSION}_b{BUILD}.pyw"))
        _prune_backups(bdir)
        tmp = script_path + ".new"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, script_path)
        _runlog(f"updated to build {info['build']} ({info['version']}), restarting")
        subprocess.Popen([sys.executable, script_path, "--after-update"], cwd=BASE_DIR,
                         creationflags=0x00000008 | 0x00000200)   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP

    def _do_update(info):
        def worker():
            try:
                apply_update(info)
                ui_root.after(0, lambda: os._exit(0))
            except Exception as e:
                _runlog("UPDATE FAILED:\n" + traceback.format_exc())
                ui_root.after(0, lambda: messagebox.showerror("numbinder", _L("Update failed: ", "Update failed: ") + str(e)))
        threading.Thread(target=worker, daemon=True).start()

    def on_update_info(info, manual):
        app = MACRO_CONFIG["AppSettings"]
        if not info:
            if manual: messagebox.showinfo("numbinder", _L("Could not check for updates.", "Could not check for updates."))
            return
        if info["build"] <= BUILD:
            if manual: messagebox.showinfo("numbinder", _L("You have the latest version.", "You have the latest version."))
            return
        if app.get("auto_update", False):
            _do_update(info)
            return
        base = int(app.get("update_remind_base", BUILD))
        if manual or info["build"] - base >= 10:
            ask = _L(f"Version {info['version']} (build {info['build']}) is available. Update now?\n\n"
                     "Yes — update and restart. No — remind me in 10 builds.",
                     f"Version {info['version']} (build {info['build']}) is available. Update now?\n\n"
                     "Yes: update and restart. No: remind me after 10 more builds.")
            if messagebox.askyesno("numbinder", ask):
                _do_update(info)
            else:
                app["update_remind_base"] = info["build"]
                save_config()

    def check_updates(manual=False):
        def worker():
            info = fetch_latest_release()
            ui_root.after(0, lambda: on_update_info(info, manual))
        threading.Thread(target=worker, daemon=True).start()

    def _periodic_update_check():
        check_updates(False)
        ui_root.after(6 * 3600 * 1000, _periodic_update_check)

    def _maybe_show_whats_new():
        app = MACRO_CONFIG["AppSettings"]
        last = app.get("last_seen_build")
        if last is None:
            app["last_seen_build"] = BUILD
            save_config()
            return
        if int(last) < BUILD:
            app["last_seen_build"] = BUILD
            save_config()
            show_changelog()

    def show_changelog():
        win = tk.Toplevel(ui_root)
        win.title(f"numbinder {VERSION}")
        win.configure(bg="#111111")
        win.geometry("420x520")
        win.transient(ui_root)
        txt = tk.Text(win, bg="#111111", fg="#e8e8e8", font=("Segoe UI", 10), wrap="word", bd=0, padx=24, pady=18, highlightthickness=0)
        txt.pack(fill=tk.BOTH, expand=True)
        txt.tag_configure("ver", font=("Segoe UI", 12, "bold"), foreground="#1db954", spacing1=8)
        for ver, items in CHANGELOG:
            txt.insert(tk.END, f"{ver}\n", "ver")
            for it in items:
                txt.insert(tk.END, f"  •  {it}\n")
        txt.configure(state="disabled")
        RoundBtn(win, text="Close", bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=win.destroy).pack(fill=tk.X, padx=24, pady=12, ipady=6)

    def on_auto_update_toggle(var):
        MACRO_CONFIG["AppSettings"]["auto_update"] = bool(var.get())
        save_config()

    def create_update_section(parent):
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        tk.Label(parent, text=_L("Updates", "Updates"), fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
        auto_var = tk.BooleanVar(value=MACRO_CONFIG["AppSettings"].get("auto_update", False))
        create_switch_row(parent, _L("Install updates automatically", "Install updates automatically"), auto_var,
                          command=lambda: on_auto_update_toggle(auto_var))
        tk.Label(parent, text=f"{VERSION} · build {BUILD}", fg="#777777", bg=_bg, font=("Consolas", 9)).pack(anchor="w", padx=30)
        RoundBtn(parent, text="What's new", bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=show_changelog).pack(fill=tk.X, padx=40, pady=(5, 5), ipady=5)
        RoundBtn(parent, text=_L("Check for updates", "Check for updates"), bg="#2d2d2d", fg="#ffffff",
                 font=("Segoe UI", 10), command=lambda: check_updates(True)).pack(pady=6, ipadx=10, ipady=4)
        RoundBtn(parent, text=_L("Go to GitHub page", "Go to GitHub page"), bg="#2d2d2d", fg="#ffffff",
                 font=("Segoe UI", 10), command=lambda: webbrowser.open(f"https://github.com/{GH_REPO}")).pack(pady=(0, 6), ipadx=10, ipady=4)

    def save_config():
        with open(PATH_CONFIG, "w", encoding="utf-8") as f:
            json.dump(MACRO_CONFIG, f, indent=4, ensure_ascii=False)

    def set_appwindow():
        try:
            hwnd = ctypes.windll.user32.GetParent(ui_root.winfo_id())
            if hwnd:
                style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                style = style & ~0x00000080
                style = style | 0x00040000 
                ctypes.windll.user32.SetWindowLongW(hwnd, -20, style)
        except: pass
    
    ui_root.after(100, set_appwindow)

    class _DWM_MARGINS(ctypes.Structure):
        _fields_ = [("cxLeftWidth", ctypes.c_int), ("cxRightWidth", ctypes.c_int),
                    ("cyTopHeight", ctypes.c_int), ("cyBottomHeight", ctypes.c_int)]

    def dwm_round_corners(hwnd, style=2):
        # 33 = DWMWA_WINDOW_CORNER_PREFERENCE. 0=нет,1=малое,2=большое -> DONOTROUND/ROUNDSMALL/ROUND
        try:
            corner_map = {0: 1, 1: 3, 2: 2}
            pref = ctypes.c_int(corner_map.get(int(style), 2))
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(pref), ctypes.sizeof(pref))
        except Exception:
            pass

    def dwm_soft_shadow(hwnd):
        # Настоящая нативная мягкая тень DWM по краю безрамочного окна
        try:
            margins = _DWM_MARGINS(1, 1, 1, 1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            pass

    def apply_window_region(w, h):
        """Window corner rounding: the radius comes from DevSettings['corner_radius'] (default 32 px)."""
        try:
            r = int(MACRO_CONFIG.get("DevSettings", {}).get("corner_radius", 32))
            hwnd = ctypes.windll.user32.GetParent(ui_root.winfo_id()) or ui_root.winfo_id()
            if r <= 0:
                ctypes.windll.user32.SetWindowRgn(hwnd, None, True); return
            gdi = ctypes.windll.gdi32
            gdi.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
            gdi.CreateRoundRectRgn.restype = ctypes.c_void_p
            ctypes.windll.user32.SetWindowRgn.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
            rgn = gdi.CreateRoundRectRgn(0, 0, int(w) + 1, int(h) + 1, r * 2, r * 2)
            ctypes.windll.user32.SetWindowRgn(hwnd, rgn, True)   # система сама освобождает регион
        except Exception:
            pass

    def apply_native_style():
        try:
            hwnd = ctypes.windll.user32.GetParent(ui_root.winfo_id())
            if not hwnd: return
            dev = MACRO_CONFIG.get("DevSettings", {})
            dwm_soft_shadow(hwnd)
        except Exception:
            pass

    ui_root.after(100, apply_native_style)

    AUTOSTART_TASK = "numbinderAutoStart"
    _NOWIN = 0x08000000

    def _autostart_exe():
        return sys.executable.replace("python.exe", "pythonw.exe")

    def task_exists():
        r = subprocess.run(["schtasks", "/query", "/tn", AUTOSTART_TASK], capture_output=True, creationflags=_NOWIN)
        return r.returncode == 0

    def task_enable():
        """Option 1: Task Scheduler task at logon. PowerShell is used so the task has no 72-hour limit and runs on battery."""
        q = lambda x: str(x).replace("'", "''")
        ps = (f"$a = New-ScheduledTaskAction -Execute '{q(_autostart_exe())}' -Argument '\"{q(script_path)}\"' -WorkingDirectory '{q(os.path.dirname(script_path))}'; "
              f"$t = New-ScheduledTaskTrigger -AtLogOn -User '{q(os.environ.get('USERNAME', ''))}'; "
              f"$s = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Seconds 0); "
              f"Register-ScheduledTask -TaskName '{AUTOSTART_TASK}' -Action $a -Trigger $t -Settings $s -Force | Out-Null")
        r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                           capture_output=True, text=True, creationflags=_NOWIN)
        msg = (r.stderr or r.stdout or "").strip()
        return r.returncode == 0, msg[:300]

    def task_disable():
        subprocess.run(["schtasks", "/delete", "/tn", AUTOSTART_TASK, "/f"], capture_output=True, creationflags=_NOWIN)

    def startup_file():
        return os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup", "numbinder_autostart.cmd")

    def startup_enable():
        """Option 2: a small .cmd file in the Startup folder. No admin rights, no Task Scheduler."""
        try:
            with open(startup_file(), "w", encoding="utf-8") as f:
                f.write("@echo off\r\n")
                f.write(f'cd /d "{os.path.dirname(script_path)}"\r\n')
                f.write(f'start "" "{_autostart_exe()}" "{script_path}"\r\n')
            return True, startup_file()
        except Exception as e:
            return False, str(e)

    def startup_disable():
        try:
            if os.path.exists(startup_file()): os.remove(startup_file())
        except Exception:
            pass

    def autostart_active():
        return task_exists() or os.path.exists(startup_file())

    def toggle_task_scheduler(enable):
        """Returns (ok, message). Used by the Start with Windows switch (option 1)."""
        if enable:
            return task_enable()
        task_disable()
        return True, ""

    def show_autostart_help(msg=""):
        win = tk.Toplevel(ui_root)
        win.title("Start with Windows")
        win.configure(bg="#111111")
        win.geometry("420x440")
        win.transient(ui_root)
        bg_c = "#111111"
        tk.Label(win, text=_L("Start with Windows", "Start with Windows"), fg="#ffffff", bg=bg_c, font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=24, pady=(18, 4))
        tk.Label(win, text="Not starting with system? Pick one of the two ways below.", fg="#aaaaaa", bg=bg_c, font=("Segoe UI", 10), wraplength=370, justify=tk.LEFT).pack(anchor="w", padx=24)
        status = tk.Label(win, text=msg, fg="#f5d142", bg=bg_c, font=("Segoe UI", 9), wraplength=370, justify=tk.LEFT)
        status.pack(anchor="w", padx=24, pady=(8, 0))

        def card(title, text, is_on, toggle):
            box = tk.Frame(win, bg="#1e1e1e")
            box.pack(fill=tk.X, padx=24, pady=8)
            tk.Label(box, text=title, fg="#ffffff", bg="#1e1e1e", font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 2))
            tk.Label(box, text=text, fg="#bbbbbb", bg="#1e1e1e", font=("Segoe UI", 9), wraplength=340, justify=tk.LEFT).pack(anchor="w", padx=14)
            st = tk.Label(box, text="● on" if is_on() else "○ off", fg="#1db954" if is_on() else "#888888", bg="#1e1e1e", font=("Segoe UI", 9, "bold"))
            st.pack(anchor="w", padx=14, pady=(4, 2))
            btn_txt = tr("Turn off") if is_on() else tr("Turn on")
            def act():
                ok, m = toggle(not is_on())
                status.config(text=m if not ok else "")
                if not ok: status.config(text="Failed: " + m)
                win.destroy(); show_autostart_help(status.cget("text"))
                sync_autostart_switch()
            RoundBtn(box, text=btn_txt, bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=act).pack(fill=tk.X, padx=14, pady=(4, 12), ipady=5)

        def toggle_scheduler(on):
            if on: return task_enable()
            task_disable(); return True, ""
        def toggle_startup(on):
            if on: return startup_enable()
            startup_disable(); return True, ""

        card("1. Task Scheduler (recommended)",
             "Creates a task that starts numbinder at every logon. No time limit, runs on battery too.",
             task_exists, toggle_scheduler)
        card("2. Startup folder",
             "Puts numbinder_autostart.cmd into your Startup folder. Use this if Task Scheduler is blocked on your PC.",
             lambda: os.path.exists(startup_file()), toggle_startup)

        RoundBtn(win, text="Close", bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=win.destroy).pack(fill=tk.X, padx=24, pady=(4, 16), ipady=6)

    autostart_holder = {"var": None}
    def sync_autostart_switch():
        try:
            on = autostart_active()
            MACRO_CONFIG["AppSettings"]["autostart"] = on
            save_config()
            if autostart_holder["var"] is not None: autostart_holder["var"].set(on)
        except Exception:
            pass

    class RoundBtn(tk.Canvas):
        """Rounded button on a Canvas. Replaces tk.Button and accepts the same main options."""
        RADIUS = 10
        def __init__(self, parent, text="", command=None, bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10),
                     activebackground=None, activeforeground=None, padx=16, pady=7, width=None, height=None,
                     cursor="hand2", state="normal", **kw):
            import tkinter.font as _tf
            for k in ("relief", "bd", "borderwidth", "anchor", "textvariable", "overrelief", "highlightthickness",
                      "takefocus", "justify", "wraplength", "image", "compound", "activeforeground_"):
                kw.pop(k, None)
            self._text, self._cmd = text, command
            self._bg, self._fg, self._font = bg, fg, font
            self._abg = activebackground or bg
            self._afg = activeforeground or fg
            self._state, self._hover = state, False
            f = _tf.Font(font=font)
            tw = f.measure(text or " ")
            if width: tw = f.measure("0" * int(width))
            w = tw + 2 * padx
            h = f.metrics("linespace") + 2 * pady
            try: parent_bg = parent.cget("bg")
            except Exception: parent_bg = "#111111"
            super().__init__(parent, width=w, height=h, bg=parent_bg, highlightthickness=0, bd=0, cursor=cursor, **kw)
            self.not_scrollable = True   # колесо мыши над кнопкой прокручивает окно, а не кнопку
            self.bind("<Configure>", lambda e: self._draw())
            self.bind("<Enter>", self._on_enter)
            self.bind("<Leave>", self._on_leave)
            self.bind("<ButtonRelease-1>", self._on_click)
            self._draw()

        def _on_enter(self, e=None):
            self._hover = True
            self._draw()
        def _on_leave(self, e=None):
            self._hover = False
            self._draw()
        def _on_click(self, e=None):
            if self._state == "disabled" or not self._cmd: return
            if 0 <= e.x <= self.winfo_width() and 0 <= e.y <= self.winfo_height():
                self._cmd()

        def _draw(self):
            try:
                self.delete("all")
                w = self.winfo_width()
                h = self.winfo_height()
                if w < 4: w = int(float(super().cget("width")))
                if h < 4: h = int(float(super().cget("height")))
                fill = self._abg if (self._hover and self._state != "disabled") else self._bg
                fg = self._afg if (self._hover and self._state != "disabled") else self._fg
                r = max(0, min(self.RADIUS, h / 2, w / 2))
                x1, y1, x2, y2 = 1, 1, w - 1, h - 1
                pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
                       x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
                self.create_polygon(pts, smooth=True, fill=fill, outline=fill)
                self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self._font)
            except tk.TclError:
                pass

        def configure(self, cnf=None, **kw):
            if cnf: kw.update(cnf)
            redraw = False
            for k in ("text", "bg", "fg", "command", "state", "activebackground", "activeforeground"):
                if k in kw:
                    v = kw.pop(k); redraw = True
                    if k == "text": self._text = v
                    elif k == "bg": self._bg = v; self._abg = self._abg if "activebackground" in kw else v
                    elif k == "fg": self._fg = v; self._afg = v
                    elif k == "command": self._cmd = v
                    elif k == "state": self._state = v
                    elif k == "activebackground": self._abg = v
                    elif k == "activeforeground": self._afg = v
            for k in ("relief", "bd", "borderwidth", "anchor", "textvariable", "activeforeground_", "overrelief", "justify", "wraplength"):
                kw.pop(k, None)
            if kw:
                try: super().configure(**kw)
                except tk.TclError: pass
            try:
                parent_bg = self.master.cget("bg")
                super().configure(bg=parent_bg)
            except Exception:
                pass
            if redraw: self._draw()
        config = configure

        def cget(self, key):
            if key == "text": return self._text
            if key == "bg": return self._bg
            if key == "fg": return self._fg
            return super().cget(key)

    class AnimatedSwitch(tk.Canvas):
        def __init__(self, parent, variable, command=None, width=44, height=22, **kwargs):
            bg_c = kwargs.pop("bg", "#121212")
            super().__init__(parent, width=width, height=height, bg=bg_c, highlightthickness=0, cursor="hand2", **kwargs)
            self.not_scrollable = True
            self.variable = variable
            self.command = command
            self.state = variable.get()
            self.width = width
            self.height = height
            self.knob_radius = height // 2 - 2
            self.off_x = self.knob_radius + 2
            self.on_x = width - self.knob_radius - 2
            self.progress = 1.0 if self.state else 0.0
            self.bind("<Button-1>", self.toggle)
            self.draw()

        def draw(self):
            self.delete("all")
            color = self.interpolate_color("#1db954", "#3a3a3a", self.progress)
            points = [self.height//2, 2, self.width-self.height//2, 2, self.width-self.height//2, self.height-2, self.height//2, self.height-2, self.height//2, 2]
            self.create_polygon(points, smooth=True, fill=color, outline=color)
            current_x = self.off_x + self.progress * (self.on_x - self.off_x)
            self.create_oval(current_x-self.knob_radius, self.height//2-self.knob_radius, current_x+self.knob_radius, self.height//2+self.knob_radius, fill="#ffffff", outline="")

        def toggle(self, event=None):
            self.state = not self.state
            self.variable.set(self.state)
            self.animate(1) 
            if self.command: self.command()

        def animate(self, step):
            try:
                if not self.winfo_exists(): return
            except tk.TclError:
                return
            steps = 20 
            t_linear = step / steps
            eased = (t_linear**3 * -0.375) + (t_linear**2 * -0.25) + (t_linear * 1.625)
            eased = max(0.0, min(1.0, eased))
            if self.state: self.progress = eased
            else: self.progress = 1.0 - eased
            try:
                self.draw()
            except tk.TclError:
                return
            if step < steps: ui_root.after(15, lambda: self.animate(step + 1))

        def interpolate_color(self, hex1, hex2, p):
            r1, g1, b1 = int(hex1[1:3], 16), int(hex1[3:5], 16), int(hex1[5:7], 16)
            r2, g2, b2 = int(hex2[1:3], 16), int(hex2[3:5], 16), int(hex2[5:7], 16)
            r = int(r1 + (r2 - r1) * (1-p)); g = int(g1 + (g2 - g1) * (1-p)); b = int(b1 + (b2 - b1) * (1-p))
            return f"#{r:02x}{g:02x}{b:02x}"

    class FluentSlider(tk.Canvas):
        # Тонкая дорожка + круглый бегунок, как в Windows 11 Settings — вместо
        # стандартного объёмного tk.Scale. Тянуть можно и кликом, и драгом.
        # Поддерживает variable=<IntVar/DoubleVar> с полноценной двусторонней
        # привязкой (как у tk.Scale): var.set() снаружи двигает ползунок,
        # драг ползунка пишет обратно в var.
        def __init__(self, parent, from_, to, value=None, variable=None, command=None, width=160, height=20, is_float=False, **kwargs):
            bg_c = kwargs.pop("bg", "#1e1e1e")
            super().__init__(parent, width=width, height=height, bg=bg_c, highlightthickness=0, cursor="hand2", **kwargs)
            self.not_scrollable = True
            self.from_, self.to = from_, to
            self.command = command
            self.is_float = is_float
            self.variable = variable
            self.value = value if value is not None else (variable.get() if variable is not None else from_)
            self.radius = 7
            self._trace_guard = False
            self._trace_name = None
            if self.variable is not None:
                self._trace_name = self.variable.trace_add("write", self._on_var_write)
            self.bind("<Button-1>", self._on_drag)
            self.bind("<B1-Motion>", self._on_drag)
            self.bind("<Configure>", lambda e: self._redraw())
            self.bind("<Destroy>", self._on_destroy)
            self._redraw()

        def _on_var_write(self, *args):
            if self._trace_guard or self.variable is None: return
            try:
                v = self.variable.get()
            except Exception:
                return
            self.value = v
            self._redraw()
            if self.command: self.command(self.value)

        def _on_destroy(self, e=None):
            if self.variable is not None and self._trace_name is not None:
                try: self.variable.trace_remove("write", self._trace_name)
                except Exception: pass

        def _cur_w(self):
            w = self.winfo_width()
            return w if w > 1 else int(self["width"])

        def _x_for_value(self, v):
            pad = self.radius + 2
            span = max(1e-9, (self.to - self.from_))
            frac = max(0.0, min(1.0, (v - self.from_) / span))
            return pad + frac * (self._cur_w() - pad * 2)

        def _value_for_x(self, x):
            pad = self.radius + 2
            frac = max(0.0, min(1.0, (x - pad) / max(1, (self._cur_w() - pad * 2))))
            v = self.from_ + frac * (self.to - self.from_)
            return v if self.is_float else round(v)

        def _redraw(self):
            self.delete("all")
            pad = self.radius + 2
            w = self._cur_w()
            y = int(self["height"]) // 2
            x = self._x_for_value(self.value)
            self.create_line(pad, y, w - pad, y, fill="#3a3a3a", width=4, capstyle=tk.ROUND)
            if x > pad:
                self.create_line(pad, y, x, y, fill="#1db954", width=4, capstyle=tk.ROUND)
            self.create_oval(x - self.radius, y - self.radius, x + self.radius, y + self.radius, fill="#ffffff", outline="")

        def _on_drag(self, e):
            self.value = self._value_for_x(e.x)
            self._redraw()
            if self.variable is not None:
                self._trace_guard = True
                try: self.variable.set(self.value)
                finally: self._trace_guard = False
            if self.command: self.command(self.value)

        def get(self): return self.value
        def set(self, v):
            self.value = v
            self._redraw()

    # --- DRAG & OMNI-RESIZE ---
    # Перетаскивание по координатам экрана (x_root/y_root). Координаты относительно канваса
    # дают обратную связь: окно сдвигается, канвас сдвигается, и отрисовка дёргается.
    def start_move(e): ui_root._mv = (e.x_root - ui_root.winfo_x(), e.y_root - ui_root.winfo_y())
    def stop_move(e): ui_root._mv = None
    def do_move(e):
        off = getattr(ui_root, "_mv", None)
        if off: ui_root.geometry(f"+{e.x_root - off[0]}+{e.y_root - off[1]}")

    main_frame = tk.Frame(ui_root)
    main_frame.pack(fill=tk.BOTH, expand=True)
    canvas_numpad = tk.Canvas(main_frame, highlightthickness=0)
    canvas_numpad.bind("<Leave>", lambda e: canvas_numpad.config(cursor=""))
    canvas_numpad.pack(fill=tk.BOTH, expand=True)
    canvas_numpad.is_main_canvas = True

    def _hex_to_rgba(hexcolor, alpha_pct):
        try:
            r = int(hexcolor[1:3], 16); g = int(hexcolor[3:5], 16); b = int(hexcolor[5:7], 16)
        except Exception:
            r, g, b = 29, 185, 84
        a = int(max(0, min(100, float(alpha_pct))) * 255 / 100)
        return (r, g, b, a)

    def render_crosshair_image(p, size=160):
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        cx, cy = size // 2, size // 2

        main_rgba = _hex_to_rgba(p.get("color", "#1db954"), p.get("opacity", 100))
        out_rgba = _hex_to_rgba(p.get("outline_color", "#000000"), p.get("outline_opacity", 100))
        use_outline = bool(p.get("outline_enabled", True))
        out_w = max(0, int(p.get("outline_thickness", 1)))

        shape = p.get("shape", "cross")
        gap = int(p.get("gap", 4))
        length = max(0, int(p.get("line_length", 10)))
        thick = max(1, int(p.get("line_thickness", 2)))

        if shape in ("cross", "t") and length > 0:
            segs = [
                ("top", 0, -gap, 0, -gap - length),
                ("bottom", 0, gap, 0, gap + length),
                ("left", -gap, 0, -gap - length, 0),
                ("right", gap, 0, gap + length, 0),
            ]
            if shape == "t":
                segs = [s for s in segs if s[0] != "top"]
            if use_outline and out_w > 0:
                for _, x1, y1, x2, y2 in segs:
                    draw.line([(cx + x1, cy + y1), (cx + x2, cy + y2)], fill=out_rgba, width=thick + out_w * 2)
            for _, x1, y1, x2, y2 in segs:
                draw.line([(cx + x1, cy + y1), (cx + x2, cy + y2)], fill=main_rgba, width=thick)
        elif shape == "circle":
            r = max(1, gap + length)
            if use_outline and out_w > 0:
                draw.ellipse([cx - r - out_w, cy - r - out_w, cx + r + out_w, cy + r + out_w], outline=out_rgba, width=thick + out_w * 2)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=main_rgba, width=thick)

        if p.get("center_dot", True) or shape == "dot":
            dr = max(1, int(p.get("dot_size", 3)) // 2)
            if use_outline and out_w > 0:
                draw.ellipse([cx - dr - out_w, cy - dr - out_w, cx + dr + out_w, cy + dr + out_w], fill=out_rgba)
            draw.ellipse([cx - dr, cy - dr, cx + dr, cy + dr], fill=main_rgba)

        rot = float(p.get("rotation", 0) or 0)
        if rot % 360:
            img = img.rotate(-rot, resample=Image.BICUBIC, center=(cx, cy))
        return img

    def encode_crosshair_code(p):
        try:
            raw = json.dumps(p, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            return base64.urlsafe_b64encode(raw).decode("ascii")
        except Exception:
            return ""

    def decode_crosshair_code(code):
        raw = base64.urlsafe_b64decode(code.strip().encode("ascii"))
        return json.loads(raw.decode("utf-8"))

    # --- СТРУКТУРА ОВЕРЛЕЕВ (НАСТРОЙКИ И КОНФИГУРАТОР) ---
    def create_scrollable_overlay():
        wrapper = tk.Frame(main_frame)
        canvas = tk.Canvas(wrapper, bg="#1e1e1e", highlightthickness=0)
        scroll = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        content = tk.Frame(canvas, bg="#1e1e1e")
        canvas.configure(yscrollcommand=scroll.set)
        
        # Мы больше не показываем scrollbar в UI, чтобы было красиво,
        # так как добавили умный скролл колёсиком
        # scroll.pack(side=tk.RIGHT, fill=tk.Y) 
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        window_id = canvas.create_window((0,0), window=content, anchor="nw")
        
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(window_id, width=e.width))
        content.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        
        return wrapper, canvas, content

    config_bg_frame, config_canvas, config_content = create_scrollable_overlay()
    settings_bg_frame, settings_canvas, settings_content = create_scrollable_overlay()
    crosshair_bg_frame, crosshair_canvas, crosshair_content = create_scrollable_overlay()

    # --- СИСТЕМА АВТОПАТЧЕЙ ---
    # --- САНДБОКС ---
    def open_dev_sandbox():
        box = tk.Toplevel(ui_root)
        box.title("Dev Sandbox")
        box.geometry("420x640")
        box.minsize(300, 400)
        box.configure(bg="#1e1e1e")
        box.attributes("-topmost", True)
        
        m_fr = tk.Frame(box, bg="#1e1e1e")
        m_fr.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(m_fr, bg="#1e1e1e", highlightthickness=0)
        scrollbar = tk.Scrollbar(m_fr, orient="vertical", command=canvas.yview)
        scroll_fr = tk.Frame(canvas, bg="#1e1e1e")
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.create_window((0, 0), window=scroll_fr, anchor="nw", tags="win")

        blocks = []
        class Collapsible(tk.Frame):
            def __init__(self, title):
                super().__init__(scroll_fr, bg="#252525", bd=1, relief=tk.FLAT)
                self.show = tk.BooleanVar(value=True)
                self.btn = RoundBtn(self, text=f"▼ {title}", bg="#333", fg="#f5d142", anchor="w", font=("Consolas", 10, "bold"), bd=0, cursor="hand2", command=self.toggle)
                self.btn.pack(fill=tk.X)
                self.content = tk.Frame(self, bg="#1e1e1e")
                self.content.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                blocks.append(self)
            def toggle(self):
                if self.show.get():
                    self.content.pack_forget()
                    self.btn.config(text=self.btn.cget("text").replace("▼", "▶"))
                    self.show.set(False)
                else:
                    self.content.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
                    self.btn.config(text=self.btn.cget("text").replace("▶", "▼"))
                    self.show.set(True)
                ui_root.after(10, reflow)

        def update_val(key, val, is_float=False):
            MACRO_CONFIG["DevSettings"][key] = float(val) if is_float else int(float(val))
            draw_numpad()
            
        def create_slider(parent, label, key, from_, to, res, default_val, is_float=False):
            fr = tk.Frame(parent, bg="#1e1e1e"); fr.pack(fill=tk.X, pady=1)
            tk.Label(fr, text=label, fg="#ccc", bg="#1e1e1e", font=("Segoe UI", 8)).pack(side=tk.LEFT)
            sc = tk.Scale(fr, from_=from_, to=to, resolution=res, orient=tk.HORIZONTAL, bg="#1e1e1e", fg="#1db954", highlightthickness=0, command=lambda v, k=key, f=is_float: update_val(k, v, f))
            sc.set(MACRO_CONFIG.get("DevSettings", {}).get(key, default_val)); sc.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5,0))

        def set_color(key):
            import tkinter.colorchooser as cc
            c = cc.askcolor(title=tr("Color"), color=MACRO_CONFIG.get("DevSettings", {}).get(key, "#ffffff"))[1]
            if c: MACRO_CONFIG["DevSettings"][key] = c; draw_numpad()
            
        def create_color_btn(parent, label, key):
            RoundBtn(parent, text=label, bg="#333", fg="#fff", bd=0, cursor="hand2", command=lambda: set_color(key)).pack(fill=tk.X, pady=2)
        
        b_theme = Collapsible(tr("APPEARANCE (Windows 11 native)"))
        create_color_btn(b_theme.content, tr("Header color"), "theme_grad_top")
        create_color_btn(b_theme.content, tr("Surface color"), "theme_grad_bot")

        b_win = Collapsible(tr("GRID GEOMETRY"))
        create_slider(b_win.content, "Scale", "scale", 0.5, 2.0, 0.01, 1.11, True)
        create_slider(b_win.content, "Base", "base_size", 40, 100, 1, 81)
        create_slider(b_win.content, "Spacing", "spacing", 50, 120, 1, 79)
        create_color_btn(b_win.content, tr("Button ON"), "color_active")
        create_color_btn(b_win.content, tr("Button OFF"), "color_inactive")

        b_txt = Collapsible(tr("GENERAL TEXT"))
        create_slider(b_txt.content, "X", "text_x", 0, 60, 1, 29)
        create_slider(b_txt.content, "Y", "text_y", 0, 60, 1, 21)
        create_slider(b_txt.content, "Size", "text_size", 5, 25, 1, 12)

        b_nlk = Collapsible(tr("NUMLOCK TEXT"))
        create_slider(b_nlk.content, "X", "text_x_nlk", 0, 80, 1, 29)
        create_slider(b_nlk.content, "Y", "text_y_nlk", 0, 80, 1, 21)
        create_slider(b_nlk.content, "Size", "text_size_nlk", 5, 25, 1, 12)

        b_ent = Collapsible(tr("ENTER TEXT"))
        create_slider(b_ent.content, "X", "text_x_ent", 0, 80, 1, 29)
        create_slider(b_ent.content, "Y", "text_y_ent", 0, 80, 1, 21)
        create_slider(b_ent.content, "Size", "text_size_ent", 5, 25, 1, 12)

        b_hov = Collapsible(tr("HOVER EFFECTS"))
        create_slider(b_hov.content, "Scale", "hover_scale", 1.0, 2.0, 0.01, 1.32, True)
        create_slider(b_hov.content, tr("Move away from cursor (px)"), "hover_y", 0, 50, 1, 3)
        create_slider(b_hov.content, tr("Tilt (°)"), "hover_tilt", 0, 20, 1, 3)
        create_slider(b_hov.content, tr("Blur"), "hover_blur", 0, 50, 1, 22)
        create_color_btn(b_hov.content, tr("Glow color"), "color_glow")

        bottom_fr = tk.Frame(box, bg="#1e1e1e")
        bottom_fr.pack(fill=tk.X, side=tk.BOTTOM)
        RoundBtn(bottom_fr, text=tr("SAVE ALL"), bg="#cc2929", fg="#fff", font=("Consolas", 11, "bold"), bd=0, cursor="hand2", command=lambda: [save_config(), box.destroy()]).pack(fill=tk.X, padx=20, pady=15, ipady=8)

        def reflow(e=None):
            w = canvas.winfo_width()
            if w <= 10: return
            col_width = 250
            cols = max(1, w // col_width)
            actual_col_w = (w - (cols+1)*10) // cols
            col_heights = [10] * cols
            
            for child in blocks:
                c = col_heights.index(min(col_heights))
                x = 10 + c * (actual_col_w + 10)
                y = col_heights[c]
                ch = child.winfo_reqheight()
                child.place(x=x, y=y, width=actual_col_w)
                col_heights[c] += ch + 10
                
            scroll_fr.configure(height=max(col_heights) + 20, width=w)
            canvas.configure(scrollregion=canvas.bbox("all"))

        canvas.bind("<Configure>", lambda e: ui_root.after(10, reflow))

    # --- ЭКРАН ГЛОБАЛЬНЫХ НАСТРОЕК ---
    labels_var = tk.BooleanVar(value=MACRO_CONFIG["AppSettings"].get("show_labels", True))
    
    def on_labels_toggle():
        MACRO_CONFIG["AppSettings"]["show_labels"] = labels_var.get()
        save_config()
        draw_numpad()
    
    def show_modules_warning(on_accept):
        w = tk.Toplevel(ui_root)
        w.title(_L("numbinder — modules: important warning", "numbinder — modules: important warning"))
        w.configure(bg="#111111")
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        ww, wh = min(900, sw - 80), min(640, sh - 120)
        w.geometry(f"{ww}x{wh}+{(sw - ww) // 2}+{(sh - wh) // 2}")
        w.transient(ui_root)
        w.grab_set()
        tk.Label(w, text="⚠  " + _L("WARNING: modules are code that runs on your computer",
                                    "WARNING: modules are code that runs on your computer"),
                 fg="#ffb4a8", bg="#111111", font=("Segoe UI", 16, "bold"), wraplength=ww - 60, justify="left").pack(anchor="w", padx=30, pady=(28, 12))
        body = _L(
"""Модуль — это обычный Python-файл (.py). Когда вы его устанавливаете и назначаете кнопке, он выполняется с теми же правами, что и numbinder.

Модуль может:
  • читать, изменять и удалять любые файлы, доступные вашей учётной записи;
  • запускать любые программы и команды;
  • читать и менять буфер обмена (включая пароли, которые вы копировали);
  • отправлять нажатия клавиш и мыши в любое окно;
  • обращаться к интернету и отправлять ваши данные куда угодно;
  • работать с правами администратора, если вы их дали numbinder.

numbinder не проверяет модули на безопасность и не может гарантировать, что модуль безвреден.

Ставьте только те модули, чьему коду вы доверяете: написанные вами или взятые из источника, которому вы доверяете. Перед установкой откройте файл и прочитайте его, если вы умеете читать Python.""",
"""A module is an ordinary Python file (.py). Once you install it and assign it to a button, it runs with the same rights as numbinder.

A module can:
  • read, change and delete any files your Windows account can access;
  • start any programs and commands;
  • read and change the clipboard (including passwords you copied);
  • send key and mouse input to any window;
  • access the internet and send your data anywhere;
  • run with administrator rights if you gave numbinder those.

numbinder does not check modules for safety and cannot guarantee that a module is harmless.

Only install modules whose code you trust: ones you wrote yourself or got from a source you trust. Before installing, open the file and read it if you know Python.""")
        box = tk.Text(w, wrap="word", bg="#1b1b1b", fg="#e8e8e8", relief=tk.FLAT, font=("Segoe UI", 11), padx=20, pady=16, height=1)
        box.insert("1.0", body)
        box.config(state="disabled")
        box.pack(fill=tk.BOTH, expand=True, padx=30, pady=(0, 16))
        btns = tk.Frame(w, bg="#111111")
        btns.pack(fill=tk.X, padx=30, pady=(0, 24))
        def _accept():
            w.destroy()
            on_accept()
        def _cancel():
            w.destroy()
        RoundBtn(btns, text=_L("Cancel", "Cancel"), command=_cancel, bg="#2a2a2a", fg="#e8e8e8", activebackground="#3a3a3a",
                  activeforeground="#ffffff", relief=tk.FLAT, font=("Segoe UI", 11), padx=22, pady=8).pack(side=tk.RIGHT, padx=(12, 0))
        RoundBtn(btns, text=_L("I understand the risks, continue", "I understand the risks, continue"), command=_accept, bg="#8a2b22", fg="#ffffff",
                  activebackground="#a8362b", activeforeground="#ffffff", relief=tk.FLAT, font=("Segoe UI", 11, "bold"), padx=22, pady=8).pack(side=tk.RIGHT)

    def _refresh_type_dropdowns():
        try:
            for w2 in row_type.winfo_children():
                if isinstance(w2, ttk.Combobox): w2.config(values=type_options())
        except Exception:
            pass

    def install_module_dialog():
        def _proceed():
            path = filedialog.askopenfilename(title=_L("Выберите файл модуля (.py)", "Choose a module file (.py)"),
                                              filetypes=[("Python", "*.py")])
            if not path: return
            try:
                import shutil
                os.makedirs(MODULES_DIR, exist_ok=True)
                shutil.copy2(path, os.path.join(MODULES_DIR, os.path.basename(path)))
            except Exception as e:
                messagebox.showerror("numbinder", _L("Could not copy the module:\n", "Could not copy the module:\n") + str(e))
                return
            _load_modules()
            _refresh_type_dropdowns()
            messagebox.showinfo("numbinder", _L("Module installed. It will appear in the button Type list.",
                                                "Module installed. It now appears in the button «Type» list."))
        if MACRO_CONFIG["AppSettings"].get("modules_warning_ack", False):
            _proceed()
        else:
            def _after_ack():
                MACRO_CONFIG["AppSettings"]["modules_warning_ack"] = True
                save_config()
                _proceed()
            show_modules_warning(_after_ack)

    def open_modules_folder():
        try:
            os.makedirs(MODULES_DIR, exist_ok=True)
            os.startfile(MODULES_DIR)
        except Exception as e:
            messagebox.showerror("numbinder", str(e))

    def create_modules_section(parent):
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        row = tk.Frame(parent, bg=_bg)
        row.pack(fill=tk.X, padx=30, pady=8)
        tk.Label(row, text=_L("Modules", "Modules"), fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        RoundBtn(row, text=_L("Open folder", "Open folder"), command=open_modules_folder, bg="#2a2a2a", fg="#e8e8e8",
                  activebackground="#3a3a3a", activeforeground="#ffffff", relief=tk.FLAT, font=("Segoe UI", 10), padx=12, pady=4).pack(side=tk.RIGHT, padx=(8, 0))
        RoundBtn(row, text=_L("Install module…", "Install module…"), command=install_module_dialog, bg="#2a2a2a", fg="#e8e8e8",
                  activebackground="#3a3a3a", activeforeground="#ffffff", relief=tk.FLAT, font=("Segoe UI", 10), padx=12, pady=4).pack(side=tk.RIGHT)

    # ================= СИНХРОНИЗАЦИЯ ПАПОК (DEV) =================
    NUMBS_SRC = r"C:\numbs"
    NUMBS_TARGETS = ("numbinder", "!upload")

    def sync_numbs_folders():
        """Копирует всё из C:\\numbs в C:\\numbs\\numbinder и C:\\numbs\\!upload с заменой.
        Сами целевые папки в копирование не попадают, поэтому они не вкладываются друг в друга."""
        import shutil
        src = NUMBS_SRC
        if not os.path.isdir(src):
            return False, _L(f"Folder not found: {src}", f"Folder not found: {src}")
        targets = [os.path.join(src, n) for n in NUMBS_TARGETS]
        skip = {n.lower() for n in NUMBS_TARGETS}
        for t in targets:
            os.makedirs(t, exist_ok=True)
        copied = 0
        for name in os.listdir(src):
            if name.lower() in skip: continue
            full = os.path.join(src, name)
            for t in targets:
                dst = os.path.join(t, name)
                if os.path.isdir(full):
                    shutil.copytree(full, dst, dirs_exist_ok=True)
                else:
                    shutil.copy2(full, dst)
            copied += 1
        _runlog(f"sync_numbs: copied {copied} item(s) from {src} to {', '.join(targets)}")
        return True, copied

    def on_sync_numbs():
        try:
            ok, info = sync_numbs_folders()
        except Exception as e:
            _runlog("SYNC ERROR:\n" + traceback.format_exc())
            ok, info = False, str(e)
        if ok:
            messagebox.showinfo("numbinder", _L(f"Done. Items copied: {info}",
                                                f"Done. Items copied: {info}"))
        else:
            messagebox.showerror("numbinder", str(info))

    def build_settings_screen():
        ui_root.osd_preview_mode = True
        ui_root.after(100, lambda: globals().get('force_osd_preview', lambda: None)())
        for widget in settings_content.winfo_children(): widget.destroy()
        
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        settings_canvas.config(bg=_bg)
        settings_content.config(bg=_bg)
        
        tk.Label(settings_content, text=tr("Global settings"), fg="#ffffff", bg=_bg, font=("Segoe UI", 16, "bold")).pack(pady=(20, 10), anchor="w", padx=40)
        btn_frame_set = tk.Frame(settings_content, bg=_bg)
        btn_frame_set.pack(fill=tk.X, pady=(0, 10), padx=40)
        RoundBtn(btn_frame_set, text=tr("Back"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11), borderwidth=0, cursor="hand2", command=lambda: show_main_screen()).pack(fill=tk.X, expand=True, ipady=6)
        
        create_modules_section(settings_content)
        create_update_section(settings_content)

        autostart_var = tk.BooleanVar(value=MACRO_CONFIG["AppSettings"].get("autostart", False))
        autostart_holder["var"] = autostart_var
        def on_autostart_toggle():
            want = autostart_var.get()
            ok, msg = toggle_task_scheduler(want)
            if want and not ok:
                autostart_var.set(False)
                MACRO_CONFIG["AppSettings"]["autostart"] = False
                save_config()
                show_autostart_help("Task Scheduler failed: " + msg)
                return
            if not want: startup_disable()
            MACRO_CONFIG["AppSettings"]["autostart"] = want
            save_config()

        auto_row = tk.Frame(settings_content, bg=_bg)
        auto_row.pack(fill=tk.X, padx=40, pady=8)
        tk.Label(auto_row, text=tr("Start with Windows"), bg=_bg, fg="#e8e8e8", font=("Segoe UI", 11)).pack(side=tk.LEFT)
        AnimatedSwitch(auto_row, autostart_var, bg=_bg, command=on_autostart_toggle).pack(side=tk.RIGHT)

        hint_row = tk.Frame(settings_content, bg=_bg)
        hint_row.pack(fill=tk.X, padx=40, pady=(0, 6))
        tk.Label(hint_row, text="Not starting with system? Try ", bg=_bg, fg="#aaaaaa", font=("Segoe UI", 9)).pack(side=tk.LEFT)
        other_lbl = tk.Label(hint_row, text="other ways", bg=_bg, fg="#f5d142", font=("Segoe UI", 9, "bold underline"), cursor="hand2")
        other_lbl.pack(side=tk.LEFT)
        other_lbl.bind("<Button-1>", lambda e: show_autostart_help())
        tk.Label(hint_row, text=".", bg=_bg, fg="#aaaaaa", font=("Segoe UI", 9)).pack(side=tk.LEFT)

        snd_var = tk.BooleanVar(value=MACRO_CONFIG["AppSettings"].get("action_sound", True))
        def on_snd_toggle():
            MACRO_CONFIG["AppSettings"]["action_sound"] = snd_var.get()
            save_config()
        snd_row = tk.Frame(settings_content, bg=_bg)
        snd_row.pack(fill=tk.X, padx=40, pady=8)
        tk.Label(snd_row, text=tr("Sound on button press"), bg=_bg, fg="#e8e8e8", font=("Segoe UI", 11)).pack(side=tk.LEFT)
        AnimatedSwitch(snd_row, snd_var, bg=_bg, command=on_snd_toggle).pack(side=tk.RIGHT)

        vol_row = tk.Frame(settings_content, bg=_bg)
        vol_row.pack(fill=tk.X, padx=40, pady=5)
        tk.Label(vol_row, text=tr("Sound volume"), bg=_bg, fg="#e8e8e8", font=("Segoe UI", 10)).pack(side=tk.LEFT)
        snd_start = int(MACRO_CONFIG["AppSettings"].get("action_sound_volume", 100))
        snd_lbl = tk.Label(vol_row, text=f"{snd_start}%", fg="#1db954", bg=_bg, font=("Segoe UI", 9, "bold"), width=5, anchor="e")
        snd_lbl.pack(side=tk.RIGHT, padx=(5, 0))
        def on_snd_volume(v):
            MACRO_CONFIG["AppSettings"]["action_sound_volume"] = int(v)
            snd_lbl.config(text=f"{int(v)}%")
            save_config()
        snd_slider = FluentSlider(vol_row, from_=0, to=100, value=snd_start, bg=_bg, command=on_snd_volume)
        snd_slider.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        snd_slider.bind("<ButtonRelease-1>", lambda e: play_action_sound(force=True), add="+")

        tk.Label(settings_content, text=tr("Notifications (OSD)"), fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
        
        def update_app_val(key, val, is_float=False):
            MACRO_CONFIG["AppSettings"][key] = float(val) if is_float else int(float(val))
            save_config()
            if 'force_osd_preview' in globals(): globals()['force_osd_preview']()
            
        def create_osd_slider(label, key, from_, to, res, is_float=False):
            fr = tk.Frame(settings_content, bg=_bg); fr.pack(fill=tk.X, padx=40, pady=5)
            tk.Label(fr, text=label, fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
            start_val = MACRO_CONFIG["AppSettings"].get(key, DEFAULT_CONFIG["AppSettings"][key])
            val_lbl = tk.Label(fr, text=(f"{start_val:.1f}" if is_float else str(int(start_val))), fg="#1db954", bg=_bg, font=("Segoe UI", 9, "bold"), width=4, anchor="e")
            val_lbl.pack(side=tk.RIGHT, padx=(5, 0))
            def _on_change(v, k=key, f=is_float):
                val_lbl.config(text=(f"{v:.1f}" if f else str(int(v))))
                update_app_val(k, v, f)
            sc = FluentSlider(fr, from_=from_, to=to, value=start_val, is_float=is_float, bg=_bg, command=_on_change)
            sc.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10,0))

        create_osd_slider(tr("Size (Scale)"), "osd_scale", 0.5, 3.0, 0.1, True)
        create_osd_slider(tr("Position X (%)"), "osd_x", 0, 100, 1)
        create_osd_slider(tr("Position Y (%)"), "osd_y", 0, 100, 1)

        tk.Label(settings_content, text=tr("Notification colors"), fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
        osd_color_vars = []
        def add_osd_color(label, key, default):
            var = tk.StringVar(value=MACRO_CONFIG["AppSettings"].get(key, default))
            row = create_color_row(settings_content, label, var)
            row.winfo_children()[1].config(bg=var.get())
            def on_change(*_):
                MACRO_CONFIG["AppSettings"][key] = var.get()
                save_config()
                try: row.winfo_children()[1].config(bg=var.get())
                except Exception: pass
                force_osd_preview()
            var.trace_add("write", on_change)
            osd_color_vars.append((var, default))
        add_osd_color(tr("Text"), "osd_text_color", "#cccccc")
        add_osd_color(tr("Text glow"), "osd_glow_color", "#ebebeb")
        add_osd_color(tr("Background"), "osd_bg_color", "#202020")
        add_osd_color(tr("Outline"), "osd_border_color", "#c7c7c7")
        def reset_osd_colors():
            for v, d in osd_color_vars: v.set(d)
        _rr = tk.Frame(settings_content, bg=_bg); _rr.pack(fill=tk.X, padx=40, pady=(5, 5))
        RoundBtn(_rr, text="↺", bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 12), borderwidth=0, cursor="hand2", command=reset_osd_colors).pack(side=tk.RIGHT, ipadx=9, ipady=5)

        tk.Label(settings_content, text=_L("Button colors", "Button colors"), fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
        btn_color_vars = []
        def add_btn_color(label, key, default):
            var = tk.StringVar(value=MACRO_CONFIG["DevSettings"].get(key, default))
            row = create_color_row(settings_content, label, var)
            swatch = row.winfo_children()[1]
            def on_btn_color(*_):
                MACRO_CONFIG["DevSettings"][key] = var.get()
                save_config()
                try: swatch.config(bg=var.get(), activebackground=var.get())
                except Exception: pass
                try: draw_numpad()
                except Exception: pass
            var.trace_add("write", on_btn_color)
            btn_color_vars.append((var, default))
        add_btn_color(tr("Button ON"), "color_active", "#1db954")
        add_btn_color(tr("Button OFF"), "color_inactive", "#3a3a3a")
        add_btn_color(tr("Hover glow"), "color_glow", "#1db954")
        def reset_btn_colors():
            for v, d in btn_color_vars: v.set(d)
        _rr2 = tk.Frame(settings_content, bg=_bg); _rr2.pack(fill=tk.X, padx=40, pady=(5, 5))
        RoundBtn(_rr2, text="↺", bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 12), borderwidth=0, cursor="hand2", command=reset_btn_colors).pack(side=tk.RIGHT, ipadx=9, ipady=5)

        tk.Label(settings_content, text=tr("Crosshairs"), fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
        RoundBtn(settings_content, text=tr("Open crosshair designer"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=lambda: open_crosshair_designer()).pack(fill=tk.X, padx=40, pady=5, ipady=6)

        tk.Label(settings_content, text=tr("Experimental"), fg="#e05a4f", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
        ext_var = tk.BooleanVar(value=extended_on())
        def on_ext_toggle():
            if ext_var.get(): show_extended_warning()
            else: set_extended_keyboard(False)
        ext_row = tk.Frame(settings_content, bg=_bg)
        ext_row.pack(fill=tk.X, padx=40, pady=(4, 0))
        tk.Label(ext_row, text=tr("Extended keyboard"), bg=_bg, fg="#e8e8e8", font=("Segoe UI", 11)).pack(side=tk.LEFT)
        AnimatedSwitch(ext_row, ext_var, bg=_bg, command=on_ext_toggle).pack(side=tk.RIGHT)
        tk.Label(settings_content, text=tr("Bind the F-keys, arrows, Insert…Page Down, Right Alt and Right Ctrl. Not recommended."),
                 bg=_bg, fg="#e05a4f", font=("Segoe UI", 9), wraplength=330, justify=tk.LEFT).pack(anchor="w", padx=40, pady=(2, 6))

        if MACRO_CONFIG["AppSettings"].get("dev_unlocked", False):
            dev_var = tk.BooleanVar(value=MACRO_CONFIG["AppSettings"].get("dev_enabled", False))
            def on_dev_toggle():
                MACRO_CONFIG["AppSettings"]["dev_enabled"] = dev_var.get()
                save_config()
                build_settings_screen() 
            
            dev_row = tk.Frame(settings_content, bg=_bg)
            dev_row.pack(fill=tk.X, padx=40, pady=(20, 5))
            tk.Label(dev_row, text=tr("DEV mode (hot patches)"), bg=_bg, fg="#f5d142", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
            AnimatedSwitch(dev_row, dev_var, bg=_bg, command=on_dev_toggle).pack(side=tk.RIGHT)

            if dev_var.get():
                RoundBtn(settings_content, text=_L("Sync C:\\numbs", "Sync C:\\numbs"), bg="#1f6f3a", fg="#ffffff",
                         font=("Segoe UI", 10, "bold"), command=on_sync_numbs).pack(pady=4, ipadx=10, ipady=6)


    # Кнопки, которые нельзя назначить: NumLock и numpad '/'. Хук их не перехватывает,
    # поэтому RU-точка на той же клавише больше не срабатывает как макрос.
    LOCKED_SC = ("69", "53")
    NUMPAD_LAYOUT = [
        ("69", 0, 0, 1, 1), ("53", 1, 0, 1, 1), ("55", 2, 0, 1, 1), ("74", 3, 0, 1, 1),
        ("71", 0, 1, 1, 1), ("72", 1, 1, 1, 1), ("73", 2, 1, 1, 1), ("78", 3, 1, 1, 2),
        ("75", 0, 2, 1, 1), ("76", 1, 2, 1, 1), ("77", 2, 2, 1, 1),
        ("79", 0, 3, 1, 1), ("80", 1, 3, 1, 1), ("81", 2, 3, 1, 1), ("284", 3, 3, 1, 2),
        ("82", 0, 4, 2, 1), ("83", 2, 4, 1, 1)
    ]
    # Extended keyboard (experimental). Columns are relative to the numpad (col 0 = NumLock).
    # Ins..PgDn and arrows sit where they are on a real keyboard; F-keys are a compact 3x4 block;
    # RAlt and RCtrl are under the F-keys (RCtrl next to the arrows, like on a keyboard).
    # Extended scan codes are stored as scan + 256 (e.g. Up = 72 + 256 = 328).
    EXT_LAYOUT = [
        ("59", -6.8, 0, 1, 1), ("60", -5.8, 0, 1, 1), ("61", -4.8, 0, 1, 1),
        ("62", -6.8, 1, 1, 1), ("63", -5.8, 1, 1, 1), ("64", -4.8, 1, 1, 1),
        ("65", -6.8, 2, 1, 1), ("66", -5.8, 2, 1, 1), ("67", -4.8, 2, 1, 1),
        ("68", -6.8, 3, 1, 1), ("87", -5.8, 3, 1, 1), ("88", -4.8, 3, 1, 1),
        ("312", -5.8, 4, 1, 1), ("285", -4.8, 4, 1, 1),
        ("338", -3.4, 0, 1, 1), ("327", -2.4, 0, 1, 1), ("329", -1.4, 0, 1, 1),
        ("339", -3.4, 1, 1, 1), ("335", -2.4, 1, 1, 1), ("337", -1.4, 1, 1, 1),
        ("328", -2.4, 3, 1, 1),
        ("331", -3.4, 4, 1, 1), ("336", -2.4, 4, 1, 1), ("333", -1.4, 4, 1, 1),
    ]
    EXT_COLS = 6.8   # how many columns the extended block adds on the left

    def extended_on():
        return bool(MACRO_CONFIG.get("AppSettings", {}).get("extended_kb", False))

    def ext_offset():
        """Extra width on the left of the window when the extended keyboard is on."""
        if not extended_on(): return 0
        return int(round(EXT_COLS * float(MACRO_CONFIG.get("DevSettings", {}).get("spacing", 79))))

    def cur_win_w():
        return WIN_W + ext_offset()

    def current_layout():
        return NUMPAD_LAYOUT + (EXT_LAYOUT if extended_on() else [])

    allowed_keys = set()   # keys the hook may take over; read by the hook thread
    def update_allowed_keys():
        new = {b[0] for b in NUMPAD_LAYOUT}
        if extended_on(): new |= {b[0] for b in EXT_LAYOUT}
        allowed_keys.clear(); allowed_keys.update(new)
    update_allowed_keys()

    btn_img_cache = {}
    hover_cache = {}
    btn_geom_cache = {}
    pil_cache = {}
    hover_state = {"sc": None, "target": None, "p": 0.0, "job": None, "mx": 0, "my": 0, "refs": [],
                   "press_t0": None, "press_sc": None}
    HOVER_EASE = 0.3   # скорость догонялки анимации (0..1), чем больше — тем резче

    # нажатие: кнопка сжимается на 8% и возвращается; та же экспоненциальная кривая, что у попапа
    PRESS_DOWN_MS, PRESS_UP_MS, PRESS_DEPTH = 90, 260, 0.08
    _EXP_LIM = 1 - 2 ** -10

    def _press_scale(ms):
        if ms < PRESS_DOWN_MS:
            return 1.0 - PRESS_DEPTH * (1 - 2 ** (-10 * ms / PRESS_DOWN_MS)) / _EXP_LIM
        if ms < PRESS_DOWN_MS + PRESS_UP_MS:
            t = (ms - PRESS_DOWN_MS) / PRESS_UP_MS
            return 1.0 - PRESS_DEPTH + PRESS_DEPTH * (1 - 2 ** (-10 * t)) / _EXP_LIM
        return 1.0

    def _press_active():
        t0 = hover_state["press_t0"]
        return t0 is not None and (time.perf_counter() - t0) * 1000.0 < PRESS_DOWN_MS + PRESS_UP_MS

    def start_press(sc):
        hover_state["press_t0"] = time.perf_counter()
        hover_state["press_sc"] = sc
        if hover_state["job"] is None:
            hover_state["last_t"] = None
            render_hover_frame()

    def _set_static(sc, visible):
        canvas_numpad.itemconfig(f"static_{sc}", state="normal" if visible else "hidden")

    def _cache_pil(key, make):
        if key not in pil_cache:
            if len(pil_cache) > 600: pil_cache.clear()
            pil_cache[key] = make()
        return pil_cache[key]

    def _tinted_pil(img_path, color, w, h):
        """Button sprite tinted to the color. Cached as a PIL image (not rotated)."""
        def make():
            img = Image.open(img_path).convert("RGBA").resize((w, h), Image.Resampling.LANCZOS)
            tr_, tg_, tb_ = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            r, g, b, a = img.split()
            r = r.point(lambda i: i * tr_ / 255); g = g.point(lambda i: i * tg_ / 255); b = b.point(lambda i: i * tb_ / 255)
            return Image.merge("RGBA", (r, g, b, a))
        return _cache_pil(("tint", img_path, color, w, h), make)

    def _glow_base_pil(img_path, color, w, h, blur):
        pad = blur * 3 + 10
        def make():
            base = Image.new("RGBA", (w + pad * 2, h + pad * 2), (0, 0, 0, 0))
            shape = _tinted_pil(img_path, color, w, h)
            base.paste(shape, (pad, pad), shape)
            return base.filter(ImageFilter.GaussianBlur(blur))
        return _cache_pil(("glow", img_path, color, w, h, blur), make), pad

    # ---- hover rendering: everything that costs time is cached ----
    # Size, tilt and glow strength are quantized, so each frame image is built once and reused.
    # The glow is blurred once per button at full hover size and only scaled after that.
    # Canvas items are reused (coords/itemconfig), not deleted and created every frame.
    hover_photo_cache = collections.OrderedDict()
    HOVER_PHOTO_MAX = 700

    def _photo_cached(key, make):
        ph = hover_photo_cache.get(key)
        if ph is not None:
            hover_photo_cache.move_to_end(key)
            return ph
        ph = make()
        if ph is None: return None
        hover_photo_cache[key] = ph
        if len(hover_photo_cache) > HOVER_PHOTO_MAX: hover_photo_cache.popitem(last=False)
        return ph

    def _body_photo(img_t, color, w, h, angle_q):
        def make():
            body = _tinted_pil(img_t, color, w, h)
            if abs(angle_q) > 0.01:
                body = body.rotate(angle_q, resample=Image.Resampling.BICUBIC)
            return ImageTk.PhotoImage(body)
        return _photo_cached(("b", img_t, color, w, h, angle_q), make)

    def _glow_full_size(gw, gh, hs_scale):
        return max(2, int(round(gw * hs_scale))), max(2, int(round(gh * hs_scale)))

    def _glow_photo(img_t, gl_c, blur, gw, gh, hs_scale, s_q, p_q):
        wmax, hmax = _glow_full_size(gw, gh, hs_scale)
        def make():
            base, _pad = _glow_base_pil(img_t, gl_c, wmax, hmax, blur)
            rel = s_q / hs_scale if hs_scale > 0 else 1.0
            if abs(rel - 1.0) > 0.005:
                g = base.resize((max(1, int(round(base.width * rel))), max(1, int(round(base.height * rel)))), Image.Resampling.BILINEAR)
            else:
                g = base.copy()
            g.putalpha(g.getchannel("A").point(lambda v, pq=p_q: int(v * pq)))
            return ImageTk.PhotoImage(g)
        return _photo_cached(("g", img_t, gl_c, blur, wmax, hmax, s_q, p_q), make)

    def _hover_items():
        it = hover_state.get("items")
        if it: return it
        c = canvas_numpad
        it = {
            "bg": c.create_image(0, 0, state="hidden", tags=("hover_fx_bg",)),
            "body": c.create_image(0, 0, state="hidden", tags=("hover_fx",)),
            "icon": c.create_image(0, 0, state="hidden", tags=("hover_fx",)),
            "text": c.create_text(0, 0, text="", anchor="nw", state="hidden", tags=("hover_fx",)),
        }
        hover_state["items"] = it
        return it

    def _hide_hover_items():
        it = hover_state.get("items")
        if not it: return
        for i in it.values():
            canvas_numpad.itemconfig(i, state="hidden")

    def _btn_img_type(geom):
        return PATH_BTN_HOR if geom["cs"] == 2 else (PATH_BTN_VERT if geom["rs"] == 2 else PATH_BTN_SINGLE)

    def _draw_hover_frame(sc, p):
        """Moves the hovered/pressed button away from the cursor and tilts it, using cached images."""
        geom = btn_geom_cache.get(sc)
        if not geom: return
        c = canvas_numpad
        dev = MACRO_CONFIG.get("DevSettings", {})
        k = geom.get("k", 1.0)
        it = _hover_items()

        dx, dy = geom["cx"] - hover_state["mx"], geom["cy"] - hover_state["my"]
        dist = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux, uy = dx / dist, dy / dist
        away = float(dev.get("hover_y", 13)) * p
        ncx, ncy = geom["cx"] + ux * away, geom["cy"] + uy * away

        pf = 1.0
        if hover_state["press_sc"] == sc and hover_state["press_t0"] is not None:
            pf = _press_scale((time.perf_counter() - hover_state["press_t0"]) * 1000.0)
        hs_scale = float(dev.get("hover_scale", 1.3))
        s_q = round((1.0 + (hs_scale - 1.0) * p) * pf * 100.0) / 100.0
        w, h = max(2, int(round(geom["w"] * s_q))), max(2, int(round(geom["h"] * s_q)))
        angle_q = round(-float(dev.get("hover_tilt", 8)) * p * ux * 2.0) / 2.0
        img_t = _btn_img_type(geom)

        # glow (under the button)
        p_q = round(p * 20.0) / 20.0
        gph = None
        if p_q > 0:
            try: gph = _glow_photo(img_t, dev.get("color_glow", "#1db954"), int(dev.get("hover_blur", 15)), geom["w"], geom["h"], hs_scale, s_q, p_q)
            except Exception: gph = None
        if gph:
            c.itemconfig(it["bg"], image=gph, state="disabled"); c.coords(it["bg"], ncx, ncy)
        else:
            c.itemconfig(it["bg"], state="hidden")

        # the button
        try: bph = _body_photo(img_t, geom["color"], w, h, angle_q)
        except Exception: bph = None
        if bph:
            c.itemconfig(it["body"], image=bph, state="disabled"); c.coords(it["body"], ncx, ncy)
        else:
            c.itemconfig(it["body"], state="hidden")

        # icon or label (moves with the button)
        drawn_icon = False
        st = MACRO_CONFIG.get(sc, {})
        if geom["is_act"] and st.get("IconPath"):
            ipath = resolve_icon(st["IconPath"])
            icolor = st.get("IconColor", "#ffffff")
            if os.path.exists(ipath):
                ic_sz = max(4, int(min(w, h) * 0.45) // 2 * 2)
                ik_key = f"icn_{sc}_{icolor}_{ic_sz}"
                if ik_key not in btn_img_cache:
                    t_icn = tint_image(ipath, icolor, ic_sz, ic_sz)
                    if t_icn: btn_img_cache[ik_key] = t_icn
                if ik_key in btn_img_cache:
                    c.itemconfig(it["icon"], image=btn_img_cache[ik_key], state="disabled"); c.coords(it["icon"], ncx, ncy)
                    drawn_icon = True
        if not drawn_icon: c.itemconfig(it["icon"], state="hidden")
        if MACRO_CONFIG["AppSettings"].get("show_labels", True) and not drawn_icon:
            tx = (ncx - w / 2) + geom["t_x"] * k * s_q
            ty = (ncy - h / 2) + geom["t_y"] * k * s_q
            c.itemconfig(it["text"], text=SC_NAMES.get(sc, sc), fill="#ffffff" if geom["is_act"] else "#888888",
                         font=("Segoe UI", max(6, int(geom["t_size"] * k * s_q)), "bold"), state="disabled")
            c.coords(it["text"], tx, ty)
        else:
            c.itemconfig(it["text"], state="hidden")

    def render_hover_frame():
        hs = hover_state
        now = time.perf_counter()
        last = hs.get("last_t") or (now - 1 / 60.0)
        dt = min(0.1, max(0.0, now - last))
        hs["last_t"] = now
        target = hs["target"]
        # another button under the cursor: put the previous one back
        if hs["sc"] is not None and target != hs["sc"]:
            _hide_hover_items()
            _set_static(hs["sc"], True)
            hs["sc"] = None; hs["p"] = 0.0
        if target is not None and hs["sc"] is None:
            hs["sc"] = target; hs["p"] = 0.0
            _set_static(target, False)

        desired = 1.0 if target is not None else 0.0
        # time-based easing: same speed at any frame rate (HOVER_EASE is the step per 1/60 s)
        a = 1.0 - (1.0 - HOVER_EASE) ** (dt * 60.0)
        p = hs["p"] + (desired - hs["p"]) * a
        if abs(desired - p) < 0.01: p = desired
        hs["p"] = p

        if hs["sc"] is not None and (p > 0.005 or _press_active()):
            _draw_hover_frame(hs["sc"], p)
        else:
            _hide_hover_items()
        if target is None and p <= 0.0 and hs["sc"] is not None:
            _set_static(hs["sc"], True)
            hs["sc"] = None

        if p != desired or _press_active():
            spent = (time.perf_counter() - now) * 1000.0
            hs["job"] = ui_root.after(max(1, int(16.6 - spent)), render_hover_frame)
        else:
            hs["job"] = None
            hs["last_t"] = None

    def set_hover_target(sc):
        """Mouse moves are coalesced: at most one render per ~8 ms, even with a 1000 Hz mouse."""
        hover_state["target"] = sc
        if hover_state["job"] is None:
            hover_state["last_t"] = None
            hover_state["job"] = ui_root.after(8, render_hover_frame)

    def _prewarm_hover():
        """Blurs the glow for every button in the background, so the first hover has no hitch."""
        dev = MACRO_CONFIG.get("DevSettings", {})
        hs_scale = float(dev.get("hover_scale", 1.3))
        gl_c = dev.get("color_glow", "#1db954")
        blur = int(dev.get("hover_blur", 15))
        todo, seen = [], set()
        for g in list(btn_geom_cache.values()):
            img_t = _btn_img_type(g)
            wm, hm = _glow_full_size(g["w"], g["h"], hs_scale)
            if (img_t, wm, hm) in seen: continue
            seen.add((img_t, wm, hm)); todo.append((img_t, wm, hm))
        def step():
            if not todo: return
            img_t, wm, hm = todo.pop()
            try: _glow_base_pil(img_t, gl_c, wm, hm, blur)
            except Exception: pass
            ui_root.after(5, step)
        ui_root.after(150, step)

    def _hit_button(x, y):
        """Button whose resting rectangle contains the point. Matches the sprite."""
        best, best_d = None, None
        for sc, g in btn_geom_cache.items():
            if abs(x - g["cx"]) <= g["w"] / 2 and abs(y - g["cy"]) <= g["h"] / 2:
                d = (x - g["cx"]) ** 2 + (y - g["cy"]) ** 2
                if best is None or d < best_d: best, best_d = sc, d
        return best

    def _canvas_cursor(cur):
        if canvas_numpad.cget("cursor") != cur: canvas_numpad.config(cursor=cur)

    def on_canvas_motion(e):
        hover_state["mx"], hover_state["my"] = e.x, e.y
        sc = _hit_button(e.x, e.y)
        if sc is None:
            _canvas_cursor(""); set_hover_target(None)
        elif sc in LOCKED_SC:
            _canvas_cursor("no"); set_hover_target(None)
        else:
            _canvas_cursor("hand2"); set_hover_target(sc)

    def on_canvas_leave(e):
        canvas_numpad.config(cursor="")
        set_hover_target(None)

    def on_canvas_click(e):
        sc = _hit_button(e.x, e.y)
        if sc is None or sc in LOCKED_SC: return
        start_press(sc)
        make_click_handler(sc)(e)

    canvas_numpad.bind("<Motion>", on_canvas_motion)
    canvas_numpad.bind("<Leave>", on_canvas_leave)
    canvas_numpad.bind("<Button-1>", on_canvas_click)

    def tint_image(img_path, target_color_hex, w_target, h_target, alpha=1.0):
        try:
            img = Image.open(img_path).convert("RGBA")
            img = img.resize((int(w_target), int(h_target)), Image.Resampling.LANCZOS)
            tr, tg, tb = int(target_color_hex[1:3], 16), int(target_color_hex[3:5], 16), int(target_color_hex[5:7], 16)
            r, g, b, a = img.split()
            r, g, b = r.point(lambda i: i * tr / 255), g.point(lambda i: i * tg / 255), b.point(lambda i: i * tb / 255)
            if alpha < 1.0: a = a.point(lambda i: int(i * alpha))
            return ImageTk.PhotoImage(Image.merge('RGBA', (r, g, b, a)))
        except: return None

    def make_click_handler(scan_code):
        def on_numpad_click(e):
            if e.state & 0x0004: # Control
                global secret_buffer
                nm = {"79":"1", "80":"2", "81":"3", "75":"4", "76":"5", "77":"6", "71":"7", "72":"8", "73":"9", "82":"0"}
                if scan_code in nm:
                    secret_buffer += nm[scan_code]
                    if len(secret_buffer) > 6: secret_buffer = secret_buffer[-6:]
                    if secret_buffer == "281236":
                        secret_buffer = ""
                        if not MACRO_CONFIG["AppSettings"].get("dev_unlocked", False):
                            MACRO_CONFIG["AppSettings"]["dev_unlocked"] = True
                            save_config()
                            messagebox.showinfo("DEV MODE", tr("🔓 Developer initialization...\n\nDEV mode unlocked!"))
            else:
                open_config_screen(scan_code)
        return on_numpad_click

    _first_place = {"done": False, "w": None}
    def draw_numpad():
        canvas_numpad.delete("all")
        btn_geom_cache.clear()
        if hover_state["job"]:
            try: ui_root.after_cancel(hover_state["job"])
            except Exception: pass
        hover_state.update({"sc": None, "target": None, "p": 0.0, "job": None, "refs": [], "press_t0": None, "press_sc": None, "items": None, "last_t": None})
        apply_native_style()
        dev = MACRO_CONFIG.get("DevSettings", {})
        labels_var.set(MACRO_CONFIG["AppSettings"].get("show_labels", True))
        
        ext_w = ext_offset()
        win_w = WIN_W + ext_w
        win_h = WIN_H
        if not _first_place["done"]:
            _first_place["done"] = True
            sw, sh = ui_root.winfo_screenwidth(), ui_root.winfo_screenheight()
            ui_root.geometry(f"{win_w}x{win_h}+{max(0, (sw - win_w) // 2)}+{max(0, (sh - win_h) // 2)}")
        elif _first_place["w"] is not None and _first_place["w"] != win_w:
            # the window grows/shrinks on the LEFT, so the numpad stays where it was on screen
            nx = ui_root.winfo_x() - (win_w - _first_place["w"])
            ui_root.geometry(f"{win_w}x{win_h}+{nx}+{ui_root.winfo_y()}")
        else:
            ui_root.geometry(f"{win_w}x{win_h}")
        _first_place["w"] = win_w
        apply_window_region(win_w, win_h)
        surface_color = dev.get("theme_grad_bot", "#202020")
        ui_root.configure(bg=surface_color)
        canvas_numpad.configure(bg=surface_color)
        
        # Область перетаскивания (сверху)
        canvas_numpad.create_rectangle(20, 0, win_w-60, 40, fill="", outline="", tags="drag_zone")
        canvas_numpad.tag_bind("drag_zone", "<ButtonPress-1>", start_move)
        canvas_numpad.tag_bind("drag_zone", "<B1-Motion>", do_move)
        canvas_numpad.tag_bind("drag_zone", "<ButtonRelease-1>", stop_move)
        
        # Центрируем элементы шапки
        header_frame = tk.Frame(canvas_numpad, bg=dev.get("theme_grad_top", "#2a2a2a"))
        canvas_numpad.create_window(win_w / 2, 40, window=header_frame, anchor="n", width=win_w - 50)
        
        tk.Label(header_frame, text=f"numbinder {VERSION}", fg="#555555", font=("Segoe UI", 10, "bold"), bg=dev.get("theme_grad_top", "#2a2a2a")).pack(side=tk.LEFT)
        
        def open_settings(): show_settings_screen()
        settings_btn = tk.Label(header_frame, text="⚙", fg="#888", font=("Segoe UI", 16), cursor="hand2", bg=dev.get("theme_grad_top", "#2a2a2a"))
        settings_btn.pack(side=tk.RIGHT, padx=(10, 0))
        settings_btn.bind("<Enter>", lambda e: [settings_btn.config(fg="#fff"), canvas_numpad.config(cursor="hand2")])
        settings_btn.bind("<Leave>", lambda e: [settings_btn.config(fg="#888"), canvas_numpad.config(cursor="")])
        settings_btn.bind("<Button-1>", lambda e: open_settings())

        def make_caption_btn(glyph, hover_bg, hover_fg, cmd, size=11):
            base_bg = dev.get("theme_grad_top", "#2a2a2a")
            lbl = tk.Label(header_frame, text=glyph, fg="#999999", font=("Segoe UI", size), cursor="hand2", bg=base_bg)
            lbl.pack(side=tk.RIGHT, ipadx=8, ipady=3)
            lbl.bind("<Enter>", lambda e: [lbl.config(bg=hover_bg, fg=hover_fg), canvas_numpad.config(cursor="hand2")])
            lbl.bind("<Leave>", lambda e: [lbl.config(bg=base_bg, fg="#999999"), canvas_numpad.config(cursor="")])
            lbl.bind("<Button-1>", lambda e: cmd())
            return lbl

        def minimize_app(): ui_root.withdraw()
        def quit_app():
            try: tray_icon.stop()
            except Exception: pass
            os._exit(0)

        # Порядок native Windows: minimize -> close (близко к правому краю, close крайний)
        make_caption_btn("─", "#3f3f3f", "#ffffff", minimize_app, size=11)
        close_btn = make_caption_btn("✕", "#c42b1c", "#ffffff", quit_app, size=10)
        
        controls_sub_fr = tk.Frame(header_frame, bg=dev.get("theme_grad_top", "#2a2a2a"))
        controls_sub_fr.pack(side=tk.BOTTOM, fill=tk.X, pady=(5, 0))
        
        if MACRO_CONFIG["AppSettings"].get("dev_enabled", False):
            RoundBtn(controls_sub_fr, text="🛠️ DEV SANDBOX", bg="#f5d142", fg="#000", font=("Segoe UI", 8, "bold"), borderwidth=0, cursor="hand2", command=open_dev_sandbox).pack(side=tk.LEFT, ipady=2, ipadx=5)
        
        AnimatedSwitch(controls_sub_fr, labels_var, bg=dev.get("theme_grad_top", "#2a2a2a"), command=on_labels_toggle).pack(side=tk.RIGHT, padx=5)
        tk.Label(controls_sub_fr, text=tr("Button labels"), bg=dev.get("theme_grad_top", "#2a2a2a"), fg="#888888", font=("Segoe UI", 9)).pack(side=tk.RIGHT)
        
        # --- ОТРИСОВКА КНОПОК ---
        BASE_SIZE = dev.get("base_size", 81)
        SPACING = dev.get("spacing", 79)
        SCALE = dev.get("scale", 1.11)
        
        grid_w = 3 * SPACING + BASE_SIZE
        grid_h = 4 * SPACING + BASE_SIZE
        START_X = ext_w + (WIN_W - grid_w) / 2
        START_Y = max(110, (win_h - grid_h) / 2 - 10) 
        
        show_lbls = MACRO_CONFIG["AppSettings"].get("show_labels", True)
        color_active = dev.get("color_active", "#1db954")
        color_inactive = dev.get("color_inactive", "#3a3a3a")
        
        if ext_w:
            # big red warning plate at the bottom
            plate = tk.Label(canvas_numpad, text=tr("⚠  EXTENDED KEYBOARD IS ON (experimental)\nIt can break normal keyboard use. Turning it off in Settings is recommended."),
                             bg="#c62828", fg="#ffffff", font=("Segoe UI", 11, "bold"), justify=tk.CENTER, cursor="hand2", pady=10)
            canvas_numpad.create_window(win_w / 2, win_h - 22, window=plate, anchor="s", width=win_w - 44)
            plate.bind("<Button-1>", lambda e: show_settings_screen())

        for btn in current_layout():
            sc, col, row, col_span, row_span = btn
            orig_w = BASE_SIZE * col_span + (SPACING - BASE_SIZE) * (col_span - 1)
            orig_h = BASE_SIZE * row_span + (SPACING - BASE_SIZE) * (row_span - 1)
            orig_x1, orig_y1 = START_X + col * SPACING, START_Y + row * SPACING
            center_x, center_y = orig_x1 + orig_w / 2, orig_y1 + orig_h / 2
            draw_w, draw_h = orig_w * SCALE, orig_h * SCALE
            x1, y1 = center_x - draw_w / 2, center_y - draw_h / 2
            
            locked = sc in LOCKED_SC
            is_active = (not locked) and sc in MACRO_CONFIG and MACRO_CONFIG[sc].get("Type") != "none"
            color = color_active if is_active else color_inactive 
            
            img_type = PATH_BTN_HOR if col_span == 2 else (PATH_BTN_VERT if row_span == 2 else PATH_BTN_SINGLE)
            cache_key = f"{sc}_{color}_{draw_w}_{draw_h}" + ("_locked" if locked else "")
            if cache_key not in btn_img_cache:
                if locked: tinted = tint_image(img_type, "#5a5a5a", draw_w, draw_h, alpha=0.35)
                else: tinted = tint_image(img_type, color, draw_w, draw_h)
                if tinted: btn_img_cache[cache_key] = tinted
            
            st_tag = f"static_{sc}"
            rect_id = canvas_numpad.create_image(center_x, center_y, image=btn_img_cache.get(cache_key), tags=(st_tag,)) if cache_key in btn_img_cache else canvas_numpad.create_polygon([x1+15,y1, x1+draw_w-15,y1, x1+draw_w,y1+15, x1+draw_w,y1+draw_h-15, x1+draw_w-15,y1+draw_h, x1+15,y1+draw_h, x1,y1+draw_h-15, x1,y1+15], smooth=True, fill=color, tags=(st_tag,))
            
            if sc == "69": t_x, t_y, t_s = dev.get("text_x_nlk", 29), dev.get("text_y_nlk", 21), int(dev.get("text_size_nlk", 12))
            elif sc == "284": t_x, t_y, t_s = dev.get("text_x_ent", 29), dev.get("text_y_ent", 21), int(dev.get("text_size_ent", 12))
            else: t_x, t_y, t_s = dev.get("text_x", 29), dev.get("text_y", 21), int(dev.get("text_size", 12))
            
            btn_geom_cache[sc] = {"w": draw_w, "h": draw_h, "cx": center_x, "cy": center_y, "cs": col_span, "rs": row_span, "color": color, "is_act": is_active, "t_x": t_x, "t_y": t_y, "t_size": t_s, "k": SCALE}

            drawn_icon = False
            if is_active and MACRO_CONFIG[sc].get("IconPath"):
                ipath = resolve_icon(MACRO_CONFIG[sc]["IconPath"])
                icolor = MACRO_CONFIG[sc].get("IconColor", "#ffffff")
                if os.path.exists(ipath):
                    ic_sz = int(min(draw_w, draw_h) * 0.45)
                    ik_key = f"icn_{sc}_{icolor}_{ic_sz}"
                    if ik_key not in btn_img_cache:
                        tinted_icn = tint_image(ipath, icolor, ic_sz, ic_sz)
                        if tinted_icn: btn_img_cache[ik_key] = tinted_icn
                    if ik_key in btn_img_cache:
                        canvas_numpad.create_image(center_x, center_y, image=btn_img_cache[ik_key], tags=(st_tag,))
                        drawn_icon = True

            if show_lbls and not drawn_icon:
                lbl_text = SC_NAMES.get(sc, sc)
                txt_color = "#ffffff" if is_active else ("#5f5f5f" if locked else "#888888")
                canvas_numpad.create_text((center_x - draw_w/2) + t_x*SCALE, (center_y - draw_h/2) + t_y*SCALE, text=lbl_text, fill=txt_color, font=("Segoe UI", int(t_s*SCALE), "bold"), anchor="nw", tags=(st_tag,))

        try: _prewarm_hover()
        except Exception: pass

    class ToolTip:
        def __init__(self, widget, text):
            self.widget = widget
            self.text = text
            self.tipwindow = None
            widget.bind("<Enter>", self.show_tip)
            widget.bind("<Leave>", self.hide_tip)

        def show_tip(self, event=None):
            if self.tipwindow or not self.text: return
            x, y, cx, cy = self.widget.bbox("insert")
            x = x + self.widget.winfo_rootx() + 25
            y = y + cy + self.widget.winfo_rooty() + 25
            self.tipwindow = tw = tk.Toplevel(self.widget)
            tw.wm_overrideredirect(True)
            tw.wm_geometry(f"+{x}+{y}")
            tw.attributes("-topmost", True)
            label = tk.Label(tw, text=self.text, justify=tk.LEFT, bg="#333333", fg="#ffffff", relief=tk.SOLID, borderwidth=1, font=("Segoe UI", 9))
            label.pack(ipadx=5, ipady=3)

        def hide_tip(self, event=None):
            tw = self.tipwindow
            self.tipwindow = None
            if tw: tw.destroy()

    # --- ЭКРАН НАСТРОЕК КНОПКИ ---
    current_edit_sc = None
    
    config_title = tk.Label(config_content, text="", fg="#ffffff", font=("Segoe UI", 16, "bold"), bg="#1e1e1e")
    config_title.pack(anchor="w", padx=30, pady=(20, 10))

    lbl_overlay_tip = tk.Label(config_content, text=tr("💡 OVERLAY\n\nShort press — On/Off\nHold — open the overlay studio"), fg="#f5d142", bg="#1e1e1e", font=("Segoe UI", 10, "bold"), justify=tk.CENTER)

    def show_info_window(title, text):
        top = tk.Toplevel(ui_root)
        top.title(title)
        top.overrideredirect(True)
        top.geometry("340x220")
        top.configure(bg="#2d2d2d")
        top.attributes("-topmost", True)
        top.geometry(f"+{ui_root.winfo_x() + 40}+{ui_root.winfo_y() + 200}")
        ui_root.after(100, lambda: (dwm_round_corners(ctypes.windll.user32.GetParent(top.winfo_id()), 1),
                                     dwm_soft_shadow(ctypes.windll.user32.GetParent(top.winfo_id()))))
        tk.Label(top, text=title, fg="#ffffff", bg="#2d2d2d", font=("Segoe UI", 12, "bold")).pack(pady=(15,0))
        tk.Label(top, text=text, fg="#cccccc", bg="#2d2d2d", font=("Segoe UI", 10), justify=tk.LEFT, wraplength=300).pack(padx=15, pady=10, expand=True)
        RoundBtn(top, text=tr("Close"), bg="#3a3a3a", fg="#fff", font=("Segoe UI", 9), borderwidth=0, cursor="hand2", command=top.destroy).pack(side=tk.BOTTOM, pady=10, ipadx=10, ipady=4)

    _dark_combo_style_done = [False]
    def _ensure_dark_combobox_style():
        if _dark_combo_style_done[0]: return
        _dark_combo_style_done[0] = True
        try:
            style = ttk.Style()
            style.theme_use("default")
            style.configure("Dark.TCombobox",
                fieldbackground="#2d2d2d", background="#2d2d2d", foreground="#ffffff",
                arrowcolor="#ffffff", bordercolor="#2d2d2d", lightcolor="#2d2d2d",
                darkcolor="#2d2d2d", selectbackground="#2d2d2d", selectforeground="#ffffff",
                borderwidth=0, relief="flat", padding=6)
            style.map("Dark.TCombobox",
                fieldbackground=[("readonly", "#2d2d2d")],
                foreground=[("readonly", "#ffffff")],
                background=[("readonly", "#2d2d2d")])
            ui_root.option_add("*TCombobox*Listbox.background", "#2d2d2d")
            ui_root.option_add("*TCombobox*Listbox.foreground", "#ffffff")
            ui_root.option_add("*TCombobox*Listbox.selectBackground", "#1db954")
            ui_root.option_add("*TCombobox*Listbox.selectForeground", "#000000")
            ui_root.option_add("*TCombobox*Listbox.font", ("Segoe UI", 10))
        except Exception:
            pass

    # ================= ЕДИНЫЙ ВЫБОР ПРИЛОЖЕНИЙ =================
    # Один список для exec, громкости и исключений clean2;0.
    # Список: запущенные приложения пользователя + ярлыки из меню «Пуск» (так видны и не запущенные).
    # Иконки берутся из exe и кэшируются PNG-файлами рядом с config.json.
    APP_CAT = {"items": None, "busy": False}
    APP_ICON_IMG = {}
    _APP_SCAN_PS = r"""
param([string]$Cache, [string]$Extra)
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}
Add-Type -AssemblyName System.Drawing
$found = @{}
$names = @{}
$sh = New-Object -ComObject WScript.Shell
$dirs = @("$env:APPDATA\Microsoft\Windows\Start Menu\Programs", "$env:ProgramData\Microsoft\Windows\Start Menu\Programs")
foreach ($d in $dirs) {
  Get-ChildItem -LiteralPath $d -Filter *.lnk -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
    $t = ''
    try { $t = $sh.CreateShortcut($_.FullName).TargetPath } catch {}
    if ($t -and $t.ToLower().EndsWith('.exe') -and (Test-Path -LiteralPath $t)) {
      $k = $t.ToLower()
      if (-not $names.ContainsKey($k)) { $names[$k] = $_.BaseName }
      $found[$k] = $t
    }
  }
}
if ($Extra -and (Test-Path -LiteralPath $Extra)) {
  foreach ($line in Get-Content -LiteralPath $Extra) {
    $t = $line.Trim()
    if ($t) { $found[$t.ToLower()] = $t }
  }
}
foreach ($k in @($found.Keys)) {
  $t = $found[$k]
  $safe = ($k -replace '[^a-z0-9]', '_')
  if ($safe.Length -gt 120) { $safe = $safe.Substring($safe.Length - 120) }
  $png = Join-Path $Cache ($safe + '.png')
  if (-not (Test-Path -LiteralPath $png)) {
    try { [System.Drawing.Icon]::ExtractAssociatedIcon($t).ToBitmap().Save($png, [System.Drawing.Imaging.ImageFormat]::Png) } catch { $png = '' }
  }
  $desc = ''
  try { $desc = [System.Diagnostics.FileVersionInfo]::GetVersionInfo($t).FileDescription } catch {}
  $nm = ''
  if ($names.ContainsKey($k)) { $nm = $names[$k] }
  Write-Output ($t + "`t" + $nm + "`t" + $desc + "`t" + $png)
}
"""

    def _app_cache_dir():
        d = os.path.join(os.path.dirname(PATH_CONFIG), "app_icons_cache")
        os.makedirs(d, exist_ok=True)
        return d

    def _load_app_catalog():
        try:
            d = _app_cache_dir()
            me = os.environ.get("USERNAME", "").lower()
            win_dir = os.environ.get("WINDIR", "C:\\Windows").lower()
            running_exes = set()
            for p in psutil.process_iter(["username", "exe"]):
                try:
                    ex = p.info.get("exe") or ""
                    if not ex.lower().endswith(".exe") or ex.lower().startswith(win_dir): continue
                    uname = (p.info.get("username") or "").lower()
                    if me and uname and not uname.endswith("\\" + me): continue
                    running_exes.add(ex)
                except Exception:
                    pass
            extra = os.path.join(d, "running.txt")
            with open(extra, "w", encoding="utf-8") as f:
                f.write("\n".join(running_exes))
            ps1 = os.path.join(d, "scan_apps.ps1")
            with open(ps1, "w", encoding="utf-8") as f:
                f.write(_APP_SCAN_PS)
            r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1,
                                "-Cache", d, "-Extra", extra], capture_output=True, creationflags=0x08000000)
            out = r.stdout.decode("utf-8", "replace")
            running_names = {os.path.basename(x).lower() for x in running_exes}
            items, seen = [], set()
            for line in out.splitlines():
                parts = [x.strip() for x in line.split("\t")]
                if len(parts) < 4: continue
                path, sc_name, desc, png = parts[0], parts[1], parts[2], parts[3]
                if not path.lower().endswith(".exe") or path.lower() in seen: continue
                seen.add(path.lower())
                exe = os.path.basename(path).lower()
                name = sc_name or desc or os.path.splitext(os.path.basename(path))[0]
                items.append({"name": name, "exe": exe, "path": path,
                              "icon": png if png and os.path.exists(png) else "",
                              "running": exe in running_names})
            items.sort(key=lambda x: (not x["running"], x["name"].lower()))
            APP_CAT["items"] = items
        except Exception as e:
            try: _runlog("app catalog error: " + repr(e))
            except Exception: pass
            APP_CAT["items"] = []
        finally:
            APP_CAT["busy"] = False

    def ensure_app_catalog():
        if APP_CAT["items"] is None and not APP_CAT["busy"]:
            APP_CAT["busy"] = True
            threading.Thread(target=_load_app_catalog, daemon=True).start()

    def app_info(exe):
        exe = (exe or "").lower()
        for it in APP_CAT["items"] or []:
            if it["exe"] == exe: return it
        return None

    def app_display_name(exe):
        it = app_info(exe)
        if it: return it["name"]
        return os.path.splitext(exe or "")[0] or (exe or "")

    def load_app_icon(png, size):
        if not png or not os.path.exists(png): return None
        key = (png, size)
        if key not in APP_ICON_IMG:
            try:
                im = Image.open(png).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)
                APP_ICON_IMG[key] = ImageTk.PhotoImage(im)
            except Exception:
                return None
        return APP_ICON_IMG[key]

    def _split_apps(text):
        out = []
        for part in re.split(r"[,;\n]+", text or ""):
            name = part.strip().lower()
            if not name: continue
            if not name.endswith(".exe"): name += ".exe"
            if name not in out: out.append(name)
        return out

    def open_app_picker(var, multi=False):
        ensure_app_catalog()
        _bg_p = "#111111"
        win = tk.Toplevel(ui_root)
        win.title(tr("Choose apps") if multi else tr("Choose app"))
        win.configure(bg=_bg_p)
        win.geometry("420x580")
        win.transient(ui_root)
        selected = set(_split_apps(var.get())) if multi else set(_split_apps(var.get())[:1])

        tk.Label(win, text=tr("Choose apps") if multi else tr("Choose app"), fg="#ffffff", bg=_bg_p,
                 font=("Segoe UI", 14, "bold")).pack(anchor="w", padx=20, pady=(16, 2))
        tk.Label(win, text=tr("Apps that are not running are taken from your Start menu. If an app is missing, launch it once and open this list again."),
                 fg="#aaaaaa", bg=_bg_p, font=("Segoe UI", 9), wraplength=370, justify=tk.LEFT).pack(anchor="w", padx=20)
        search = tk.Entry(win, bg="#2d2d2d", fg="#ffffff", insertbackground="#ffffff", borderwidth=0, font=("Segoe UI", 10))
        search.pack(fill=tk.X, padx=20, pady=(10, 6), ipady=5)
        status = tk.Label(win, text=tr("Loading apps..."), fg="#f5d142", bg=_bg_p, font=("Segoe UI", 9))
        status.pack(anchor="w", padx=20)

        wrap = tk.Frame(win, bg=_bg_p)
        wrap.pack(fill=tk.BOTH, expand=True, padx=20, pady=6)
        canvas = tk.Canvas(wrap, bg=_bg_p, highlightthickness=0, bd=0)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = tk.Frame(canvas, bg=_bg_p)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))
        def _wheel(e):
            try: canvas.yview_scroll(int(-e.delta / 120), "units")
            except Exception: pass
        canvas.bind("<MouseWheel>", _wheel); inner.bind("<MouseWheel>", _wheel)

        img_refs = []

        def pick(exe):
            if multi:
                if exe in selected: selected.discard(exe)
                else: selected.add(exe)
                render()
            else:
                var.set(exe)
                win.destroy()

        def render(*_):
            try:
                for w in inner.winfo_children(): w.destroy()
            except Exception:
                return
            img_refs.clear()
            items = APP_CAT["items"]
            if items is None:
                status.config(text=tr("Loading apps..."))
                return
            q = search.get().strip().lower()
            status.config(text="" if items else tr("No apps found. Launch an app and try again."))
            shown = 0
            for it in items:
                if q and q not in it["name"].lower() and q not in it["exe"]: continue
                shown += 1
                if shown > 250: break
                sel = it["exe"] in selected
                bg_r = "#1db954" if sel else "#1e1e1e"
                fg_main = "#000000" if sel else "#ffffff"
                fg_sub = "#1a3a24" if sel else "#888888"
                row = tk.Frame(inner, bg=bg_r, cursor="hand2")
                row.pack(fill=tk.X, pady=2)
                ic = load_app_icon(it["icon"], 26)
                icon_lbl = tk.Label(row, bg=bg_r)
                if ic:
                    img_refs.append(ic); icon_lbl.config(image=ic)
                icon_lbl.pack(side=tk.LEFT, padx=(8, 10), pady=6)
                txt = tk.Frame(row, bg=bg_r)
                txt.pack(side=tk.LEFT, fill=tk.X, expand=True)
                n_lbl = tk.Label(txt, text=it["name"], fg=fg_main, bg=bg_r, font=("Segoe UI", 10, "bold"), anchor="w")
                n_lbl.pack(anchor="w")
                sub = it["exe"] + ("   ● running" if it["running"] else "")
                e_lbl = tk.Label(txt, text=sub, fg=fg_sub, bg=bg_r, font=("Segoe UI", 8), anchor="w")
                e_lbl.pack(anchor="w")
                for w in (row, icon_lbl, txt, n_lbl, e_lbl):
                    w.bind("<Button-1>", lambda e, k=it["exe"]: pick(k))
                    w.bind("<MouseWheel>", _wheel)

        def poll():
            try:
                if not win.winfo_exists(): return
            except Exception:
                return
            if APP_CAT["items"] is None:
                win.after(200, poll)
            else:
                render()
        search.bind("<KeyRelease>", render)
        poll()

        def done():
            if multi: var.set(", ".join(sorted(selected)))
            win.destroy()
        RoundBtn(win, text=tr("Done") if multi else tr("Close"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10),
                 borderwidth=0, cursor="hand2", command=done).pack(fill=tk.X, padx=20, pady=(4, 14), ipady=6)

    def create_app_row(parent, label_text, var, multi=False, hover_text=None, ext_text=None):
        """Single row for choosing app(s): shows icons + app names, button opens the shared picker."""
        ensure_app_catalog()
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        row = tk.Frame(parent, bg=_bg)
        row.pack(fill=tk.X, padx=30, pady=8)
        lbl_frame = tk.Frame(row, bg=_bg)
        lbl_frame.pack(side=tk.LEFT)
        tk.Label(lbl_frame, text=label_text, fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        if hover_text and ext_text:
            tip = tk.Label(lbl_frame, text="ⓘ", fg="#1db954", bg=_bg, font=("Segoe UI", 9, "bold"), cursor="hand2")
            tip.pack(side=tk.LEFT, padx=5)
            ToolTip(tip, hover_text)
            tip.bind("<Button-1>", lambda e: show_info_window(label_text, ext_text))

        right = tk.Frame(row, bg=_bg)
        right.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        btn = RoundBtn(right, text=tr("Choose"), bg="#3a3a3a", fg="#fff", borderwidth=0, cursor="hand2",
                       font=("Segoe UI", 9), command=lambda: open_app_picker(var, multi=multi))
        btn.pack(side=tk.RIGHT, padx=(5, 0), ipadx=5)
        box = tk.Frame(right, bg="#2d2d2d")
        box.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=4)
        icons = tk.Frame(box, bg="#2d2d2d")
        icons.pack(side=tk.LEFT, padx=(6, 0))
        value_lbl = tk.Label(box, text="", fg="#ffffff", bg="#2d2d2d", font=("Segoe UI", 10), anchor="w")
        value_lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        icon_refs = []

        def refresh_display(*_):
            try:
                exes = _split_apps(var.get())
                if not exes:
                    value_lbl.config(text=tr("nothing selected") if multi else "—")
                for w in icons.winfo_children(): w.destroy()
                icon_refs.clear()
                for e in exes[:4]:
                    it = app_info(e)
                    im = load_app_icon(it["icon"], 20) if it else None
                    if im:
                        icon_refs.append(im)
                        tk.Label(icons, image=im, bg="#2d2d2d").pack(side=tk.LEFT, padx=(0, 4))
                names = [app_display_name(e) for e in exes]
                if exes: value_lbl.config(text=", ".join(names) if multi else names[0])
                if APP_CAT["items"] is None:
                    value_lbl.after(400, refresh_display)
            except Exception:
                pass

        var.trace_add("write", refresh_display)
        refresh_display()
        return row

    def create_input_row(parent, label_text, var, hover_text=None, ext_text=None, browse_type=None):
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        row = tk.Frame(parent, bg=_bg)
        row.pack(fill=tk.X, padx=30, pady=8)
        lbl_frame = tk.Frame(row, bg=_bg)
        lbl_frame.pack(side=tk.LEFT)
        tk.Label(lbl_frame, text=label_text, fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        if hover_text and ext_text:
            tip = tk.Label(lbl_frame, text="ⓘ", fg="#1db954", bg=_bg, font=("Segoe UI", 9, "bold"), cursor="hand2")
            tip.pack(side=tk.LEFT, padx=5)
            ToolTip(tip, hover_text) 
            tip.bind("<Button-1>", lambda e: show_info_window(label_text, ext_text))
            
        entry_frame = tk.Frame(row, bg=_bg)
        entry_frame.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
        
        entry = tk.Entry(entry_frame, textvariable=var, bg="#2d2d2d", fg="#ffffff", insertbackground="#ffffff", borderwidth=0, font=("Segoe UI", 10), justify="center")
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)

        if browse_type == "file":
            btn = RoundBtn(entry_frame, text="...", bg="#3a3a3a", fg="#fff", borderwidth=0, cursor="hand2", font=("Segoe UI", 9), command=lambda: var.set(filedialog.askopenfilename(parent=ui_root) or var.get()))
            btn.pack(side=tk.RIGHT, padx=(5,0), ipadx=5)
        elif browse_type == "process":
            def pick_proc():
                top = tk.Toplevel(ui_root)
                top.title(tr("Choose"))
                top.configure(bg="#2d2d2d")
                top.geometry("250x300")
                top.attributes("-topmost", True)
                top.geometry(f"+{ui_root.winfo_x() + 80}+{ui_root.winfo_y() + 150}")
                lb = tk.Listbox(top, bg="#2d2d2d", fg="#fff", font=("Segoe UI", 10), borderwidth=0, highlightthickness=0, selectbackground="#1db954", selectforeground="#000000")
                lb.pack(fill=tk.BOTH, expand=True)
                procs = sorted(list(set([p.info['name'] for p in psutil.process_iter(['name']) if p.info['name']])))
                for p in procs: lb.insert(tk.END, p)
                def on_sel(e): var.set(lb.get(lb.curselection())); top.destroy()
                lb.bind('<Double-1>', on_sel)
            btn = RoundBtn(entry_frame, text="...", bg="#3a3a3a", fg="#fff", borderwidth=0, cursor="hand2", font=("Segoe UI", 9), command=pick_proc)
            btn.pack(side=tk.RIGHT, padx=(5,0), ipadx=5)
        return row

    def create_dropdown_row(parent, label_text, var, options, hover_text=None, ext_text=None, command=None):
        _ensure_dark_combobox_style()
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        row = tk.Frame(parent, bg=_bg)
        row.pack(fill=tk.X, padx=30, pady=8)
        lbl_frame = tk.Frame(row, bg=_bg)
        lbl_frame.pack(side=tk.LEFT)
        tk.Label(lbl_frame, text=label_text, fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        if hover_text and ext_text:
            tip = tk.Label(lbl_frame, text="ⓘ", fg="#1db954", bg=_bg, font=("Segoe UI", 9, "bold"), cursor="hand2")
            tip.pack(side=tk.LEFT, padx=5)
            ToolTip(tip, hover_text)
            tip.bind("<Button-1>", lambda e: show_info_window(label_text, ext_text))

        combo = ttk.Combobox(row, textvariable=var, values=options, state="readonly", font=("Segoe UI", 10), style="Dark.TCombobox")
        combo.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0), ipady=2)
        if command: combo.bind("<<ComboboxSelected>>", command)
        return row

    def create_switch_row(parent, label_text, var, hover_text=None, ext_text=None, command=None):
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        row = tk.Frame(parent, bg=_bg)
        row.pack(fill=tk.X, padx=30, pady=8)
        lbl_frame = tk.Frame(row, bg=_bg)
        lbl_frame.pack(side=tk.LEFT)
        tk.Label(lbl_frame, text=label_text, fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        if hover_text and ext_text:
            tip = tk.Label(lbl_frame, text="ⓘ", fg="#1db954", bg=_bg, font=("Segoe UI", 9, "bold"), cursor="hand2")
            tip.pack(side=tk.LEFT, padx=5)
            ToolTip(tip, hover_text)
            tip.bind("<Button-1>", lambda e: show_info_window(label_text, ext_text))
            
        AnimatedSwitch(row, var, bg=_bg, command=command).pack(side=tk.RIGHT, padx=(10, 0))
        return row
        
    def create_color_row(parent, label_text, var, default=None):
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        row = tk.Frame(parent, bg=_bg)
        row.pack(fill=tk.X, padx=30, pady=8)
        tk.Label(row, text=label_text, fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        def pick_c():
            import tkinter.colorchooser as cc
            c = cc.askcolor(color=var.get())[1]
            if c: var.set(c)
            if c: btn.config(bg=c, activebackground=c)
        # квадратик-образец (children[1]) + HEX-подпись справа от него
        _c0 = var.get() or "#333333"
        btn = RoundBtn(row, bg=_c0, activebackground=_c0, width=3, height=1, bd=0, relief=tk.FLAT,
                        cursor="hand2", command=pick_c)
        btn.pack(side=tk.RIGHT, padx=(8, 0), ipadx=4, ipady=4)
        if default:
            def reset_c():
                var.set(default); btn.config(bg=default, activebackground=default)
            RoundBtn(row, text="↺", bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0,
                     cursor="hand2", command=reset_c).pack(side=tk.RIGHT, padx=(8, 0), ipadx=6, ipady=3)
        tk.Label(row, textvariable=var, fg="#aaaaaa", bg=_bg, font=("Consolas", 9)).pack(side=tk.RIGHT)
        return row

    var_type = tk.StringVar()
    var_lang = tk.StringVar()
    var_path = tk.StringVar()
    var_proc = tk.StringVar()
    var_act = tk.StringVar()
    var_sec = tk.StringVar()
    var_clean_keep = tk.StringVar()
    var_admin_bool = tk.BooleanVar()
    var_vol_dir = tk.StringVar()
    var_vol_pair = tk.StringVar()
    var_vol_steps = tk.StringVar()
    _VM_SLIDER, _VM_STEPS = _L("Smooth (slider)", "Smooth (slider)"), _L("Points (cycle)", "Points (cycle)")
    var_vol_mode = tk.StringVar(value=_VM_SLIDER)
    _VT_PROC,_VT_ACTIVE, _VT_SYSTEM = tr("Process (Process field)"), tr("Active application"), tr("Whole system")
    _VT_CODES = {_VT_PROC: "process", _VT_ACTIVE: "active", _VT_SYSTEM: "system"}
    var_vol_target = tk.StringVar(value=_VT_PROC)
    var_icon_path = tk.StringVar()
    var_icon_color = tk.StringVar()

    row_type = create_dropdown_row(config_content, "Type", var_type, type_options(), tr("Choose the main action."), tr("Determines what the button does."), lambda e: refresh_config_ui())
    row_lang = create_input_row(config_content, "Languages", var_lang,
                                tr("Languages in a cycle, comma-separated: ENG, RUS, DE, FRA, ESP, UKR"),
                                tr("Each press switches the layout to the next language in the list."))
    row_path = create_input_row(config_content, "Path", var_path, tr("File path."), tr("Specify the absolute path to the program file."), browse_type="file")
    row_proc = create_app_row(config_content, "Process", var_proc, multi=False, hover_text=tr("The app this button controls."), ext_text=tr("Pick the app from the list. Apps that are not running yet are taken from the Start menu. Icons are shown next to each app."))
    row_act = create_input_row(config_content, "ActionTime", var_act, tr("Delay before triggering (sec)."), tr("Set 0 to trigger instantly on click."))
    row_sec = create_input_row(config_content, "Hold To Action", var_sec, tr("Long hold (sec)."), tr("Hold time for the second action. Set 1.0 for the overlay."))
    MIC_MODES = [("toggle", "Toggle (press)"), ("ptt", "Push to talk (hold)"), ("ptm", "Push to mute (hold)")]
    var_mic_mode = tk.StringVar(value=MIC_MODES[0][1])
    row_mic_mode = create_dropdown_row(config_content, "Mode", var_mic_mode, [m[1] for m in MIC_MODES], tr("How the button controls the microphone."),
                                       tr("Toggle: each press mutes or unmutes the mic.\nPush to talk: the mic is on only while you hold the button.\nPush to mute: the mic is off only while you hold the button."))
    var_media = tk.StringVar(value="Play / Pause")
    row_media = create_dropdown_row(config_content, "Media key", var_media, [m[1] for m in MEDIA_KEYS], tr("Which media key to press."), tr("Play/pause, next, previous, stop or mute. Works with any media player."))
    # ---- Launch\\Close app: список действий (триггер + значение + действие) ----
    ACTION_KIND = [("launch", "Launch app"), ("close", "Close process"), ("restart", "Restart app"), ("tray", "Minimize to tray")]
    TRIGGER_KIND = [("hold", "Hold (sec)"), ("count", "Press N times")]
    actions_rows = []
    actions_box = tk.Frame(config_content, bg=MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020"))
    tk.Label(actions_box, text=tr("Actions"), fg="#e8e8e8", bg=MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020"), font=("Segoe UI", 10)).pack(anchor="w")
    tk.Label(actions_box, text=tr("Hold: the hold time closest to yours runs on release. Press N times: N quick presses in a row."),
             fg="#888888", bg=MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020"), font=("Segoe UI", 8), wraplength=330, justify=tk.LEFT).pack(anchor="w", pady=(0, 4))
    actions_list = tk.Frame(actions_box, bg=MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020"))
    actions_list.pack(fill=tk.X)

    def _add_action_row(a=None):
        _ensure_dark_combobox_style()
        a = a or {"trigger": "hold", "value": 1.0, "action": "launch"}
        _bgc = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020")
        fr = tk.Frame(actions_list, bg=_bgc)
        fr.pack(fill=tk.X, pady=2)
        trig_v = tk.StringVar(value=next(l for k, l in TRIGGER_KIND if k == a.get("trigger")) if a.get("trigger") in dict(TRIGGER_KIND) else TRIGGER_KIND[0][1])
        act_v = tk.StringVar(value=next(l for k, l in ACTION_KIND if k == a.get("action")) if a.get("action") in dict(ACTION_KIND) else ACTION_KIND[0][1])
        val_v = tk.StringVar(value=f"{float(a.get('value', 1)):g}" if a.get("trigger") != "count" else str(int(a.get("value", 1))))
        cb_t = ttk.Combobox(fr, textvariable=trig_v, values=[l for _, l in TRIGGER_KIND], state="readonly", width=13, style="Dark.TCombobox")
        cb_t.pack(side=tk.LEFT)
        ent = tk.Entry(fr, textvariable=val_v, width=4, justify="center", bg="#2d2d2d", fg="#ffffff", insertbackground="#ffffff", borderwidth=0, font=("Segoe UI", 10))
        ent.pack(side=tk.LEFT, padx=4, ipady=4)
        cb_a = ttk.Combobox(fr, textvariable=act_v, values=[l for _, l in ACTION_KIND], state="readonly", width=15, style="Dark.TCombobox")
        cb_a.pack(side=tk.LEFT)
        rec = {"frame": fr, "trig": trig_v, "val": val_v, "act": act_v}
        def _remove(rec=rec):
            try: rec["frame"].destroy()
            except Exception: pass
            if rec in actions_rows: actions_rows.remove(rec)
        RoundBtn(fr, text="✕", bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 9), borderwidth=0, cursor="hand2", command=_remove).pack(side=tk.RIGHT, ipadx=4)
        actions_rows.append(rec)

    def _set_action_rows(acts):
        for rec in list(actions_rows):
            try: rec["frame"].destroy()
            except Exception: pass
        actions_rows.clear()
        for a in acts or []: _add_action_row(a)

    def _collect_actions():
        out = []
        for r in actions_rows:
            trig = next((k for k, l in TRIGGER_KIND if l == r["trig"].get()), "hold")
            act = next((k for k, l in ACTION_KIND if l == r["act"].get()), "launch")
            try: v = float(r["val"].get().replace(",", "."))
            except ValueError: v = 1.0
            v = max(1, int(round(v))) if trig == "count" else max(0.1, v)
            out.append({"trigger": trig, "value": v, "action": act})
        return out

    RoundBtn(actions_box, text="+ Add action", bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 9), borderwidth=0, cursor="hand2",
             command=lambda: _add_action_row()).pack(fill=tk.X, pady=(6, 0), ipady=4)

    row_clean_keep = create_app_row(config_content, "Keep open", var_clean_keep, multi=True, hover_text=tr("Apps clean2;0 must NOT close."), ext_text=tr("Pick the apps clean2;0 must leave open. You can select several."))
    row_admin = create_switch_row(config_content, "Run as Admin", var_admin_bool, tr("Run as administrator."), tr("The program will be launched with maximum rights in Windows."))
    row_voltarget = create_dropdown_row(config_content, tr("Target"), var_vol_target, [_VT_PROC, _VT_ACTIVE, _VT_SYSTEM], tr("Whose volume to control."), tr("Process — the app from the Process field (for example, Spotify).\n\nActive application — the window in the foreground (its child processes too, for example in a browser).\n\nWhole system — overall Windows volume. The limit below also applies here: set it to 100 if you don't want it to interfere."), lambda e: refresh_config_ui())
    row_voldir = create_dropdown_row(config_content, "Direction", var_vol_dir, ["Up (+)", "Down (-)"], tr("Volume adjustment direction."), tr("Up: increases volume.\nDown: decreases volume."))
    row_volmode = create_dropdown_row(config_content, _L("Mode", "Mode"), var_vol_mode, [_VM_SLIDER, _VM_STEPS], _L("How the volume changes.", "How the volume changes."), _L("Smooth — volume changes while you hold the button.\n\nPoints — each press jumps to the next value in the list, cycling (for example 0 → 50 → 100 → 0).", "Smooth: volume changes while you hold the button.\n\nPoints: each press jumps to the next value in the list, cycling (for example 0 → 50 → 100 → 0)."), command=lambda e: refresh_config_ui())
    row_volsteps = create_input_row(config_content, _L("Points (%)", "Points (%)"), var_vol_steps, _L("Volume percentages, comma-separated.", "Volume percentages, comma-separated."), _L("For example: 0, 50, 100. Any number of points from 0 to 100.", "For example: 0, 50, 100. Any number of points from 0 to 100."))
    row_volpair = create_dropdown_row(config_content, "Pair Button", var_vol_pair, [tr("None")], tr("Auto-configure the second button."), tr("Lets you assign the reverse action to another button at once."))
    row_icon_path = create_input_row(config_content, "Icon Path", var_icon_path, tr("Icon path"), tr("Specify the image path (png/jpg)."), browse_type="file")
    row_icon_color = create_color_row(config_content, "Icon Color", var_icon_color, default="#ffffff")

    # --- Прицел и лёгкий макрос: поля настройки ---
    _CH_MODE_TOGGLE = tr("On/Off")
    _CH_MODE_SMART = tr("Smart (hold + cycle)")
    var_ch_mode = tk.StringVar(value=_CH_MODE_TOGGLE)
    var_ch_name = tk.StringVar()
    ch_sel = []
    hotkey_list = []
    row_ch_mode = create_dropdown_row(config_content, tr("Crosshair mode"), var_ch_mode, [_CH_MODE_TOGGLE, _CH_MODE_SMART], tr("How the button controls the crosshair."), tr("On/Off — a press shows or hides the selected crosshair.\n\nSmart — holding shows/hides it, a short press switches to the next one in the list."), lambda e: refresh_config_ui())
    row_ch_name = create_dropdown_row(config_content, tr("Crosshair"), var_ch_name, [], tr("Which crosshair to show."), tr("Crosshairs are created in the designer: Settings → Open crosshair designer."))
    lbl_ch_tip = tk.Label(config_content, text="", fg="#f5d142", bg="#1e1e1e", font=("Segoe UI", 10, "bold"), justify=tk.CENTER)
    ch_list_container = tk.Frame(config_content)
    row_hotkey = tk.Frame(config_content)
    _cf_bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020")
    lbl_type_desc = tk.Label(config_content, text="", fg="#cccccc", bg=_cf_bg, font=("Segoe UI", 10), justify=tk.CENTER, wraplength=290)
    row_ch_designer = RoundBtn(config_content, text=tr("Open crosshair designer"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=lambda: open_crosshair_designer())
    row_ch_hint = tk.Frame(config_content, bg=_cf_bg)
    lbl_ch_hint_a = tk.Label(row_ch_hint, text=tr("Already have an image of your crosshair? Try "), fg="#aaaaaa", bg=_cf_bg, font=("Segoe UI", 9))
    lbl_ch_hint_b = tk.Label(row_ch_hint, text="overlay", fg="#f5d142", bg=_cf_bg, font=("Segoe UI", 9, "bold underline"), cursor="hand2")
    lbl_ch_hint_c = tk.Label(row_ch_hint, text=tr(" instead."), fg="#aaaaaa", bg=_cf_bg, font=("Segoe UI", 9))
    lbl_ch_hint_a.pack(side=tk.LEFT); lbl_ch_hint_b.pack(side=tk.LEFT); lbl_ch_hint_c.pack(side=tk.LEFT)
    def _go_overlay(_e=None):
        var_type.set(type_to_label("overlay"))
        refresh_config_ui()
    lbl_ch_hint_b.bind("<Button-1>", _go_overlay)

    def _cfg_bg():
        return MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020")

    def render_ch_list():
        bg = _cfg_bg()
        ch_list_container.config(bg=bg)
        for w in ch_list_container.winfo_children(): w.destroy()
        tk.Label(ch_list_container, text=tr("Crosshairs in rotation (order = selection order)"), fg="#999999", bg=bg, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=tk.X, padx=30, pady=(5, 5))
        for n in list(MACRO_CONFIG.get("Crosshairs", {}).keys()):
            on = n in ch_sel
            text = f"{ch_sel.index(n) + 1}.  {n}" if on else n
            v = tk.BooleanVar(value=on)
            def toggle(nm=n, var=v):
                if var.get():
                    if nm not in ch_sel: ch_sel.append(nm)
                elif nm in ch_sel: ch_sel.remove(nm)
                config_content.after(1, render_ch_list)
            tk.Checkbutton(ch_list_container, text=text, variable=v, command=toggle, bg=bg, fg="#e8e8e8", selectcolor="#2d2d2d", activebackground=bg, activeforeground="#ffffff", font=("Segoe UI", 10), anchor="w", borderwidth=0, highlightthickness=0, cursor="hand2").pack(fill=tk.X, padx=30, pady=1)
        config_content.update_idletasks()
        config_canvas.configure(scrollregion=config_canvas.bbox("all"))

    def add_hotkey(name):
        hotkey_list.append(name)
        render_hotkey_chips()

    def remove_hotkey(i):
        if 0 <= i < len(hotkey_list): del hotkey_list[i]
        row_hotkey.after(1, render_hotkey_chips)

    def render_hotkey_chips():
        import tkinter.font as tkfont
        bg = _cfg_bg()
        row_hotkey.config(bg=bg)
        for w in row_hotkey.winfo_children(): w.destroy()
        tk.Label(row_hotkey, text=tr("Key combination"), fg="#e8e8e8", bg=bg, font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, padx=30, pady=(8, 4))
        fnt = tkfont.Font(family="Segoe UI", size=10)
        avail = max(220, WIN_W - 110)
        state = {"line": None, "used": 0}
        def put(build, width):
            if state["line"] is None or state["used"] + width > avail:
                state["line"] = tk.Frame(row_hotkey, bg=bg)
                state["line"].pack(fill=tk.X, padx=27)
                state["used"] = 0
            build(state["line"]).pack(side=tk.LEFT, padx=3, pady=3)
            state["used"] += width + 6
        for i, name in enumerate(hotkey_list):
            def build_chip(parent, i=i, name=name):
                chip = tk.Frame(parent, bg="#2d2d2d")
                tk.Label(chip, text=name, fg="#ffffff", bg="#2d2d2d", font=("Segoe UI", 10)).pack(side=tk.LEFT, padx=(8, 4), pady=4)
                x = tk.Label(chip, text="✕", fg="#999999", bg="#2d2d2d", font=("Segoe UI", 9), cursor="hand2")
                x.pack(side=tk.LEFT, padx=(0, 6))
                x.bind("<Enter>", lambda e, x=x: x.config(fg="#ff6b6b"))
                x.bind("<Leave>", lambda e, x=x: x.config(fg="#999999"))
                x.bind("<Button-1>", lambda e, i=i: remove_hotkey(i))
                return chip
            put(build_chip, fnt.measure(name) + 44)
        put(lambda parent: RoundBtn(parent, text="＋", bg="#1db954", fg="#000000", font=("Segoe UI", 11, "bold"), borderwidth=0, cursor="hand2", command=lambda: open_key_picker(add_hotkey)), 40)
        if not hotkey_list:
            tk.Label(row_hotkey, text=tr("Press “+” and choose a key on the on-screen keyboard. Keys are pressed in order and released in reverse."), fg="#777777", bg=bg, font=("Segoe UI", 9), justify=tk.LEFT, wraplength=max(220, avail)).pack(fill=tk.X, padx=30, pady=(2, 8))
        config_content.update_idletasks()
        config_canvas.configure(scrollregion=config_canvas.bbox("all"))

    _bg_cfg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
    sound_container = tk.Frame(config_content, bg=_bg_cfg)
    tk.Label(sound_container, text=tr("Process sound settings"), fg="#999999", bg=_bg_cfg, font=("Segoe UI", 11, "bold")).pack(pady=(15, 5), anchor="w", padx=30)
    
    audio_vars = {}
    def create_embedded_slider(parent, label, key, from_, to):
        fr = tk.Frame(parent, bg=_bg_cfg); fr.pack(fill=tk.X, padx=30, pady=5)
        tk.Label(fr, text=label, fg="#e8e8e8", bg=_bg_cfg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        v = tk.IntVar(value=from_)
        audio_vars[key] = v
        val_lbl = tk.Label(fr, text=str(from_), fg="#1db954", bg=_bg_cfg, font=("Segoe UI", 9, "bold"), width=4, anchor="e")
        val_lbl.pack(side=tk.RIGHT, padx=(5, 0))
        def _on_change(val): val_lbl.config(text=str(int(val)))
        sc = FluentSlider(fr, from_=from_, to=to, variable=v, bg=_bg_cfg, command=_on_change)
        sc.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10,0))

    create_embedded_slider(sound_container, tr("Volume limit %"), "limit", 10, 100)
    tk.Label(sound_container, text=tr("Quiet zone"), fg="#1db954", bg=_bg_cfg, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=30, pady=(10,0))
    create_embedded_slider(sound_container, tr("Threshold up to (%)"), "low_thresh", 1, 100)
    create_embedded_slider(sound_container, tr("Step (%)"), "low_step", 1, 20)
    create_embedded_slider(sound_container, tr("Delay (ms)"), "low_delay", 10, 500)
    tk.Label(sound_container, text=tr("Medium zone"), fg="#1db954", bg=_bg_cfg, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=30, pady=(10,0))
    create_embedded_slider(sound_container, tr("Threshold up to (%)"), "mid_thresh", 1, 100)
    create_embedded_slider(sound_container, tr("Step (%)"), "mid_step", 1, 20)
    create_embedded_slider(sound_container, tr("Delay (ms)"), "mid_delay", 10, 500)
    tk.Label(sound_container, text=tr("Loud zone"), fg="#1db954", bg=_bg_cfg, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=30, pady=(10,0))
    create_embedded_slider(sound_container, tr("Step (%)"), "high_step", 1, 20)
    create_embedded_slider(sound_container, tr("Delay (ms)"), "high_delay", 10, 500)

    def refresh_config_ui(*args):
        t = label_to_type(var_type.get())
        for r in [row_lang, row_path, row_proc, row_act, row_sec, row_clean_keep, row_admin, row_voltarget, row_volmode, row_volsteps, row_voldir, row_volpair, sound_container, lbl_overlay_tip, row_ch_mode, row_ch_name, ch_list_container, lbl_ch_tip, row_hotkey, row_ch_designer, row_ch_hint, lbl_type_desc, row_media, actions_box, row_mic_mode]: r.pack_forget()
        
        row_icon_path.pack(fill=tk.X, padx=30, pady=2)
        row_icon_color.pack(fill=tk.X, padx=30, pady=2)
            
        if t == "exec":
            for r in [row_path, row_proc, row_admin]: r.pack(fill=tk.X, padx=30, pady=2)
            actions_box.pack(fill=tk.X, padx=30, pady=2)
        elif t == "lang": row_lang.pack(fill=tk.X, padx=30, pady=2)
        elif t == "volume":
            row_voltarget.pack(fill=tk.X, padx=30, pady=2)
            row_volmode.pack(fill=tk.X, padx=30, pady=2)
            if var_vol_mode.get() == _VM_STEPS:
                row_volsteps.pack(fill=tk.X, padx=30, pady=2)
            else:
                row_voldir.pack(fill=tk.X, padx=30, pady=2)
            if var_vol_target.get() == _VT_PROC: row_proc.pack(fill=tk.X, padx=30, pady=2)
            row_volpair.pack(fill=tk.X, padx=30, pady=2)
            sound_container.pack(fill=tk.X, pady=(10, 5))
        elif t == "restart": row_act.pack(fill=tk.X, padx=30, pady=2)
        elif t == "media": row_media.pack(fill=tk.X, padx=30, pady=2)
        elif t == "mic": row_mic_mode.pack(fill=tk.X, padx=30, pady=2)
        elif t == "overlay":
            lbl_overlay_tip.pack(fill=tk.X, pady=(10, 20))
            if float(var_sec.get() or -1) <= 0: var_sec.set("1.0")
            if float(var_act.get() or -1) < 0: var_act.set("0.0")
            row_act.pack(fill=tk.X, padx=30, pady=2)
            row_sec.pack(fill=tk.X, padx=30, pady=2)
        elif t == "crosshair":
            smart = var_ch_mode.get() == _CH_MODE_SMART
            lbl_ch_tip.config(text=(tr("💡 CROSSHAIR\n\nHold — show/hide\nPress — next crosshair from the list") if smart else tr("💡 CROSSHAIR\n\nPress — show/hide the selected crosshair")))
            lbl_ch_tip.pack(fill=tk.X, pady=(10, 10))
            row_ch_mode.pack(fill=tk.X, padx=30, pady=2)
            row_ch_designer.pack(fill=tk.X, padx=30, pady=(6, 2), ipady=5)
            row_ch_hint.pack(pady=(2, 6))
            if smart:
                render_ch_list()
                ch_list_container.pack(fill=tk.X, pady=(5, 5))
                try: need_sec = float(var_sec.get() or -1) <= 0
                except ValueError: need_sec = True
                if need_sec: var_sec.set("0.5")
                row_sec.pack(fill=tk.X, padx=30, pady=2)
            else:
                row_ch_name.pack(fill=tk.X, padx=30, pady=2)
        elif t == "clean" or (t.startswith("mod:") and MODULES.get(t[4:], {}).get("info", {}).get("hold")):
            try: need_sec = float(var_sec.get() or -1) <= 0
            except ValueError: need_sec = True
            if need_sec: var_sec.set("1.0")
            row_sec.pack(fill=tk.X, padx=30, pady=2)
            if t == "clean": row_clean_keep.pack(fill=tk.X, padx=30, pady=2)
        elif t == "light macro":
            render_hotkey_chips()
            row_hotkey.pack(fill=tk.X, pady=(5, 5))
            
        _desc = type_description(t)
        lbl_type_desc.config(text=_desc, bg=MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020"))
        if _desc:
            lbl_type_desc.pack(fill=tk.X, padx=30, pady=(8, 4), after=config_bottom_fr)
        config_content.update_idletasks()
        config_canvas.configure(scrollregion=config_canvas.bbox("all"))

    def save_button_click():
        if not current_edit_sc: return
        t = label_to_type(var_type.get())
        vd = 1 if var_vol_dir.get() == "Up (+)" else -1
        
        aud_cfg = {k: v.get() for k, v in audio_vars.items()}
        current_overlay = MACRO_CONFIG.get(current_edit_sc, {}).get("Overlay", MACRO_TEMPLATE["Overlay"].copy())
        
        act_save = 0.0 if t in ("crosshair", "light macro", "media", "exec") else float(var_act.get() or 0)
        sec_save = float(var_sec.get() or -1)
        if t in ("light macro", "exec"): sec_save = -1.0
        if t == "crosshair": sec_save = max(0.1, sec_save) if var_ch_mode.get() == _CH_MODE_SMART else -1.0
        
        # --- режим громкости: плавно или точки ---
        vm = "steps" if (t == "volume" and var_vol_mode.get() == _VM_STEPS) else "slider"
        vsteps = sorted({max(0, min(100, int(x))) for x in re.findall(r"\d+", var_vol_steps.get())})
        if vm == "steps" and not vsteps: vsteps = [0, 50, 100]

        # --- пара (парная громкость) ---
        old_pair = str(MACRO_CONFIG.get(current_edit_sc, {}).get("Pair", "-1"))
        new_pair = "-1"
        if t == "volume" and var_vol_pair.get() != tr("None"):
            cand = next((k for k, v in SC_NAMES.items() if v == var_vol_pair.get()), None)
            if cand and cand != current_edit_sc and cand not in LOCKED_SC: new_pair = str(cand)

        MACRO_CONFIG[current_edit_sc] = {
            "Pair": new_pair,
            "Type": t,
            "Language": var_lang.get() if t == "lang" else "-1",
            "Path": _resolve_exec_path(var_proc.get(), var_path.get()) if t == "exec" else "-1",
            "ProcessName": var_proc.get() if t in ["exec", "volume"] else "-1",
            "ActionTime": act_save,
            "SecondActionTime": sec_save,
            "AdminRights": 1 if var_admin_bool.get() else 0,
            "VolumeDirection": vd if t == "volume" else 1,
            "VolumeTarget": _VT_CODES.get(var_vol_target.get(), "process"),
            "VolumeMode": vm,
            "VolumeSteps": vsteps,
            "CleanKeep": var_clean_keep.get().strip() if t == "clean" else "",
            "Actions": _collect_actions() if t == "exec" else [],
            "MicMode": next((m[0] for m in MIC_MODES if m[1] == var_mic_mode.get()), "toggle") if t == "mic" else "toggle",
            "MediaKey": next((m[0] for m in MEDIA_KEYS if m[1] == var_media.get()), "playpause") if t == "media" else "-1",
            "Desc": f"Macro SC {current_edit_sc}",
            "IconPath": var_icon_path.get(),
            "IconColor": var_icon_color.get(),
            "Audio": aud_cfg.copy(),
            "Overlay": current_overlay,
            "Crosshair": {"mode": "smart" if var_ch_mode.get() == _CH_MODE_SMART else "toggle", "name": var_ch_name.get(), "list": list(ch_sel)},
            "Hotkey": list(hotkey_list)
        }
        
        # разрываем старую связь, если она изменилась
        if old_pair != "-1" and old_pair != new_pair and old_pair in MACRO_CONFIG:
            MACRO_CONFIG[old_pair]["Pair"] = "-1"

        # зеркалим настройки на парную кнопку и ставим обратную связь
        if new_pair != "-1":
            prev = MACRO_CONFIG.get(new_pair, {})
            old_partner = str(prev.get("Pair", "-1"))
            if old_partner not in ("-1", current_edit_sc) and old_partner in MACRO_CONFIG:
                MACRO_CONFIG[old_partner]["Pair"] = "-1"   # партнёр уходит от своей старой пары
            partner = {**MACRO_TEMPLATE, **prev}
            partner.update({
                "Pair": current_edit_sc,
                "Type": "volume", "Language": "-1", "Path": "-1",
                "ProcessName": var_proc.get(), "ActionTime": 0.0, "SecondActionTime": -1.0,
                "AdminRights": 0, "VolumeDirection": -vd,
                "VolumeTarget": _VT_CODES.get(var_vol_target.get(), "process"),
                "Desc": f"Pair for {current_edit_sc}",
                "VolumeMode": vm, "VolumeSteps": vsteps,
                "IconPath": var_icon_path.get(), "IconColor": var_icon_color.get(),
                "Audio": aud_cfg.copy(),
            })
            partner["Overlay"] = dict(prev.get("Overlay") or MACRO_TEMPLATE["Overlay"])
            MACRO_CONFIG[new_pair] = partner

        save_config()
        # push to talk starts with the mic muted
        if t == "mic" and MACRO_CONFIG[current_edit_sc].get("MicMode") == "ptt":
            mic_command("set", True, osd=True)
        show_main_screen()

    config_bottom_fr = tk.Frame(config_content, bg=MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111"))
    config_bottom_fr.pack(pady=30, fill=tk.X, padx=30)
    RoundBtn(config_bottom_fr, text=tr("Back"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11), borderwidth=0, cursor="hand2", command=lambda: show_main_screen()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=6)
    RoundBtn(config_bottom_fr, text=tr("Save"), bg="#1db954", fg="#ffffff", font=("Segoe UI", 11, "bold"), borderwidth=0, cursor="hand2", command=save_button_click).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0), ipady=6)


    # ================= КОНСТРУКТОР ПРИЦЕЛОВ =================
    def open_crosshair_designer():
        for w in crosshair_content.winfo_children(): w.destroy()
        settings_bg_frame.place_forget()
        config_bg_frame.place_forget()
        _ensure_dark_combobox_style()

        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020")
        default_name = "Default"
        presets = MACRO_CONFIG.setdefault("Crosshairs", {})
        if default_name not in presets:
            presets[default_name] = dict(DEFAULT_CONFIG["Crosshairs"][default_name])
        ch = dict(DEFAULT_CONFIG["Crosshairs"][default_name])
        ch.update(presets[default_name])

        shape_names = {"cross": tr("Cross"), "t": tr("T-shape"), "circle": tr("Circle"), "dot": tr("Dot")}
        shape_codes = {v: k for k, v in shape_names.items()}

        def section(text, top=15):
            tk.Label(crosshair_content, text=text, fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=30, pady=(top, 0))

        tk.Label(crosshair_content, text=tr("Crosshair designer"), fg="#ffffff", bg=_bg, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=30, pady=(20, 10))

        # --- предпросмотр на разных фонах ---
        PREVIEW = 100
        preview_bgs = [(tr("Light"), "#d9d9d9"), (tr("Dark"), "#141414"), (tr("Busy"), None)]
        preview_row = tk.Frame(crosshair_content, bg=_bg)
        preview_row.pack(fill=tk.X, padx=30, pady=(0, 10))
        preview_canvases, preview_imgs = {}, {}
        noisy = [None]

        def get_noisy():
            if noisy[0] is None:
                import random
                rnd = random.Random(7)
                img = Image.new("RGBA", (PREVIEW, PREVIEW))
                d = ImageDraw.Draw(img)
                palette = [(90, 70, 60), (60, 90, 70), (70, 60, 90), (120, 100, 40), (40, 100, 120), (110, 40, 110)]
                step = 8
                for by in range(0, PREVIEW, step):
                    for bx in range(0, PREVIEW, step):
                        d.rectangle([bx, by, bx + step, by + step], fill=rnd.choice(palette) + (255,))
                noisy[0] = img
            return noisy[0]

        for label, color in preview_bgs:
            col = tk.Frame(preview_row, bg=_bg)
            col.pack(side=tk.LEFT, expand=True)
            tk.Label(col, text=label, fg="#999999", bg=_bg, font=("Segoe UI", 9)).pack()
            cv = tk.Canvas(col, width=PREVIEW, height=PREVIEW, bg="#333333", highlightthickness=1, highlightbackground="#3a3a3a")
            cv.pack(pady=4)
            preview_canvases[label] = cv

        def refresh_preview():
            try:
                ch_img = render_crosshair_image(ch, size=PREVIEW)
                for label, color in preview_bgs:
                    base = get_noisy().copy() if color is None else Image.new("RGBA", (PREVIEW, PREVIEW), color)
                    photo = ImageTk.PhotoImage(Image.alpha_composite(base.convert("RGBA"), ch_img))
                    preview_imgs[label] = photo
                    cv = preview_canvases[label]
                    cv.delete("all")
                    cv.create_image(0, 0, image=photo, anchor="nw")
            except Exception:
                pass

        # --- 1. форма и геометрия ---
        section(tr("1. Shape and geometry"), top=5)
        shape_var = tk.StringVar(value=shape_names.get(ch.get("shape", "cross"), tr("Cross")))
        def on_shape(e=None):
            ch["shape"] = shape_codes.get(shape_var.get(), "cross")
            refresh_preview()
        create_dropdown_row(crosshair_content, tr("Crosshair type"), shape_var, list(shape_codes.keys()), command=on_shape)

        dot_var = tk.BooleanVar(value=bool(ch.get("center_dot", True)))
        def on_dot():
            ch["center_dot"] = dot_var.get()
            refresh_preview()
        create_switch_row(crosshair_content, tr("Center dot"), dot_var, command=on_dot)

        sliders = {}
        def add_slider(label, key, lo, hi):
            fr = tk.Frame(crosshair_content, bg=_bg); fr.pack(fill=tk.X, padx=30, pady=8)
            tk.Label(fr, text=label, fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
            val_lbl = tk.Label(fr, text=str(ch.get(key, lo)), fg="#1db954", bg=_bg, font=("Segoe UI", 9, "bold"), width=4, anchor="e")
            val_lbl.pack(side=tk.RIGHT, padx=(5, 0))
            def _chg(v, k=key, lbl=val_lbl):
                ch[k] = int(v); lbl.config(text=str(int(v))); refresh_preview()
            sl = FluentSlider(fr, from_=lo, to=hi, value=ch.get(key, lo), bg=_bg, command=_chg)
            sl.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))
            sliders[key] = (sl, val_lbl)

        add_slider(tr("Dot size (px)"), "dot_size", 1, 10)
        add_slider(tr("Line length (px)"), "line_length", 0, 50)
        add_slider(tr("Line thickness (px)"), "line_thickness", 1, 10)
        add_slider(tr("Gap / offset (px)"), "gap", -20, 30)
        add_slider(tr("Rotation angle (°)"), "rotation", 0, 360)

        # --- 2. цвет и прозрачность ---
        section(tr("2. Color and opacity"))
        color_var = tk.StringVar(value=ch.get("color", "#1db954"))
        create_color_row(crosshair_content, tr("Crosshair color"), color_var)
        def on_color(*_):
            ch["color"] = color_var.get(); refresh_preview()
        color_var.trace_add("write", on_color)
        sw_row = tk.Frame(crosshair_content, bg=_bg); sw_row.pack(fill=tk.X, padx=30, pady=(0, 5))
        for sw_hex in ("#1db954", "#00e5ff", "#ffee00", "#ff2d95", "#ffffff"):
            RoundBtn(sw_row, bg=sw_hex, activebackground=sw_hex, width=3, borderwidth=0, cursor="hand2", command=lambda c=sw_hex: color_var.set(c)).pack(side=tk.LEFT, padx=3)
        add_slider(tr("Opacity (%)"), "opacity", 0, 100)

        # --- 3. обводка ---
        section(tr("3. Outline"))
        outline_var = tk.BooleanVar(value=bool(ch.get("outline_enabled", True)))
        def on_outline():
            ch["outline_enabled"] = outline_var.get(); refresh_preview()
        create_switch_row(crosshair_content, tr("Enable outline"), outline_var, command=on_outline)
        add_slider(tr("Outline thickness (px)"), "outline_thickness", 1, 5)
        out_color_var = tk.StringVar(value=ch.get("outline_color", "#000000"))
        create_color_row(crosshair_content, tr("Outline color"), out_color_var)
        def on_out_color(*_):
            ch["outline_color"] = out_color_var.get(); refresh_preview()
        out_color_var.trace_add("write", on_out_color)
        add_slider(tr("Outline opacity (%)"), "outline_opacity", 0, 100)

        # --- сохранённые прицелы ---
        section(tr("Saved crosshairs"), top=20)
        name_var = tk.StringVar(value=default_name)
        name_row = tk.Frame(crosshair_content, bg=_bg); name_row.pack(fill=tk.X, padx=30, pady=8)
        tk.Label(name_row, text=tr("Name"), fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        tk.Entry(name_row, textvariable=name_var, bg="#2d2d2d", fg="#ffffff", insertbackground="#ffffff", borderwidth=0, font=("Segoe UI", 10)).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0), ipady=5)

        load_var = tk.StringVar(value=default_name)
        load_row = tk.Frame(crosshair_content, bg=_bg); load_row.pack(fill=tk.X, padx=30, pady=8)
        tk.Label(load_row, text=tr("Choose saved"), fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        load_combo = ttk.Combobox(load_row, textvariable=load_var, state="readonly", font=("Segoe UI", 10), style="Dark.TCombobox")
        load_combo.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0), ipady=2)

        def refresh_names():
            names = list(MACRO_CONFIG.get("Crosshairs", {}).keys())
            load_combo["values"] = names
            if names and load_var.get() not in names: load_var.set(names[0])

        def populate(params):
            base = dict(DEFAULT_CONFIG["Crosshairs"][default_name]); base.update(params)
            ch.clear(); ch.update(base)
            shape_var.set(shape_names.get(ch.get("shape", "cross"), tr("Cross")))
            dot_var.set(bool(ch["center_dot"])); outline_var.set(bool(ch["outline_enabled"]))
            color_var.set(ch["color"]); out_color_var.set(ch["outline_color"])
            for k, (sl, lbl) in sliders.items():
                sl.set(ch[k]); lbl.config(text=str(int(ch[k])))
            refresh_preview()

        def do_save():
            nm = name_var.get().strip()
            if not nm:
                messagebox.showerror(tr("Crosshair"), tr("Enter a crosshair name.")); return
            MACRO_CONFIG.setdefault("Crosshairs", {})[nm] = dict(ch)
            save_config(); refresh_names(); load_var.set(nm)
            messagebox.showinfo(tr("Crosshair"), tr("Crosshair “{}” saved.").format(nm))

        def do_load():
            nm = load_var.get()
            preset = MACRO_CONFIG.get("Crosshairs", {}).get(nm)
            if not preset:
                messagebox.showerror(tr("Crosshair"), tr("That crosshair was not found.")); return
            name_var.set(nm); populate(preset)

        def do_delete():
            nm = load_var.get()
            if nm == default_name:
                messagebox.showerror(tr("Crosshair"), tr("The default crosshair cannot be deleted.")); return
            if nm in MACRO_CONFIG.get("Crosshairs", {}) and messagebox.askyesno(tr("Crosshair"), tr("Delete crosshair “{}”?").format(nm)):
                del MACRO_CONFIG["Crosshairs"][nm]
                save_config(); refresh_names()

        btn_row = tk.Frame(crosshair_content, bg=_bg); btn_row.pack(fill=tk.X, padx=30, pady=5)
        RoundBtn(btn_row, text=tr("Save"), bg="#1db954", fg="#000000", font=("Segoe UI", 10, "bold"), borderwidth=0, cursor="hand2", command=do_save).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3), ipady=6)
        RoundBtn(btn_row, text=tr("Load"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=do_load).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3, ipady=6)
        RoundBtn(btn_row, text=tr("Delete"), bg="#3a2020", fg="#ff8080", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=do_delete).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0), ipady=6)
        refresh_names()

        # --- код прицела ---
        section(tr("Crosshair code"), top=20)
        def do_copy_code():
            try:
                pyperclip.copy(encode_crosshair_code(ch))
                messagebox.showinfo(tr("Crosshair"), tr("Code copied to clipboard."))
            except Exception:
                messagebox.showerror(tr("Crosshair"), tr("Could not copy the code."))
        RoundBtn(crosshair_content, text=tr("Copy code"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=do_copy_code).pack(fill=tk.X, padx=30, pady=5, ipady=6)

        code_var = tk.StringVar()
        def do_apply_code():
            try:
                params = decode_crosshair_code(code_var.get())
                if not isinstance(params, dict): raise ValueError
                populate(params)
            except Exception:
                messagebox.showerror(tr("Crosshair"), tr("Invalid or corrupted crosshair code."))
        code_row = tk.Frame(crosshair_content, bg=_bg); code_row.pack(fill=tk.X, padx=30, pady=5)
        tk.Entry(code_row, textvariable=code_var, bg="#2d2d2d", fg="#ffffff", insertbackground="#ffffff", borderwidth=0, font=("Segoe UI", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        RoundBtn(code_row, text=tr("Apply code"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=do_apply_code).pack(side=tk.RIGHT, padx=(10, 0), ipadx=5, ipady=4)

        RoundBtn(crosshair_content, text=tr("Reset to default values"), bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=lambda: populate(DEFAULT_CONFIG["Crosshairs"][default_name])).pack(fill=tk.X, padx=30, pady=(10, 5), ipady=6)
        RoundBtn(crosshair_content, text=tr("Back"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11), borderwidth=0, cursor="hand2", command=lambda: show_main_screen()).pack(fill=tk.X, padx=30, pady=20, ipady=6)

        refresh_preview()
        dev = MACRO_CONFIG.get("DevSettings", {})
        win_w, win_h = WIN_W, WIN_H
        pad = 14
        crosshair_bg_frame.place(x=ext_offset() + pad, y=pad, width=win_w-pad*2, height=win_h-pad*2)
        crosshair_bg_frame.lift()


    # ================= ЛЁГКИЙ МАКРОС: клавиши и экранная клавиатура =================
    HK_VK = {"Esc": (0x1B, 0), "Backspace": (0x08, 0), "Tab": (0x09, 0), "Enter": (0x0D, 0), "Space": (0x20, 0), "Caps": (0x14, 0),
             "`": (0xC0, 0), "-": (0xBD, 0), "=": (0xBB, 0), "[": (0xDB, 0), "]": (0xDD, 0), "\\": (0xDC, 0),
             ";": (0xBA, 0), "'": (0xDE, 0), ",": (0xBC, 0), ".": (0xBE, 0), "/": (0xBF, 0),
             "LShift": (0xA0, 0), "RShift": (0xA1, 0), "LCtrl": (0xA2, 0), "RCtrl": (0xA3, 1), "LAlt": (0xA4, 0), "RAlt": (0xA5, 1),
             "LWin": (0x5B, 1), "RWin": (0x5C, 1), "Menu": (0x5D, 1),
             "PrtSc": (0x2C, 1), "ScrLk": (0x91, 0), "Pause": (0x13, 0),
             "Ins": (0x2D, 1), "Del": (0x2E, 1), "Home": (0x24, 1), "End": (0x23, 1), "PgUp": (0x21, 1), "PgDn": (0x22, 1),
             "Up": (0x26, 1), "Down": (0x28, 1), "Left": (0x25, 1), "Right": (0x27, 1),
             "NumLock": (0x90, 1), "Num/": (0x6F, 1), "Num*": (0x6A, 0), "Num-": (0x6D, 0), "Num+": (0x6B, 0), "NumEnter": (0x0D, 1), "Num.": (0x6E, 0),
             "Play/Pause": (0xB3, 0), "Next": (0xB0, 0), "Prev": (0xB1, 0), "Stop": (0xB2, 0), "Vol+": (0xAF, 0), "Vol-": (0xAE, 0), "Mute": (0xAD, 0)}
    for _i in range(10):
        HK_VK[str(_i)] = (0x30 + _i, 0)
        HK_VK[f"Num{_i}"] = (0x60 + _i, 0)
    for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ": HK_VK[_c] = (ord(_c), 0)
    for _i in range(1, 25): HK_VK[f"F{_i}"] = (0x6F + _i, 0)

    def _hk_layout():
        L = []
        def k(name, x, y, w=1, h=1, label=None): L.append((name, label or name, x, y, w, h))
        k("Esc", 0, 0)
        for i in range(4): k(f"F{i+1}", 2 + i, 0)
        for i in range(4): k(f"F{i+5}", 6.5 + i, 0)
        for i in range(4): k(f"F{i+9}", 11 + i, 0)
        k("PrtSc", 15.5, 0); k("ScrLk", 16.5, 0); k("Pause", 17.5, 0)
        k("`", 0, 1.5)
        for i, c in enumerate("1234567890"): k(c, 1 + i, 1.5)
        k("-", 11, 1.5); k("=", 12, 1.5); k("Backspace", 13, 1.5, 2)
        k("Ins", 15.5, 1.5); k("Home", 16.5, 1.5); k("PgUp", 17.5, 1.5)
        k("NumLock", 19, 1.5, label="Num"); k("Num/", 20, 1.5, label="/"); k("Num*", 21, 1.5, label="*"); k("Num-", 22, 1.5, label="-")
        k("Tab", 0, 2.5, 1.5)
        for i, c in enumerate("QWERTYUIOP"): k(c, 1.5 + i, 2.5)
        k("[", 11.5, 2.5); k("]", 12.5, 2.5); k("\\", 13.5, 2.5, 1.5)
        k("Del", 15.5, 2.5); k("End", 16.5, 2.5); k("PgDn", 17.5, 2.5)
        k("Num7", 19, 2.5, label="7"); k("Num8", 20, 2.5, label="8"); k("Num9", 21, 2.5, label="9"); k("Num+", 22, 2.5, 1, 2, label="+")
        k("Caps", 0, 3.5, 1.75)
        for i, c in enumerate("ASDFGHJKL"): k(c, 1.75 + i, 3.5)
        k(";", 10.75, 3.5); k("'", 11.75, 3.5); k("Enter", 12.75, 3.5, 2.25)
        k("Num4", 19, 3.5, label="4"); k("Num5", 20, 3.5, label="5"); k("Num6", 21, 3.5, label="6")
        k("LShift", 0, 4.5, 2.25, label="Shift")
        for i, c in enumerate("ZXCVBNM"): k(c, 2.25 + i, 4.5)
        k(",", 9.25, 4.5); k(".", 10.25, 4.5); k("/", 11.25, 4.5); k("RShift", 12.25, 4.5, 2.75, label="Shift")
        k("Up", 16.5, 4.5, label="↑")
        k("Num1", 19, 4.5, label="1"); k("Num2", 20, 4.5, label="2"); k("Num3", 21, 4.5, label="3"); k("NumEnter", 22, 4.5, 1, 2, label="Ent")
        k("LCtrl", 0, 5.5, 1.25, label="Ctrl"); k("LWin", 1.25, 5.5, 1.25, label="Win"); k("LAlt", 2.5, 5.5, 1.25, label="Alt")
        k("Space", 3.75, 5.5, 6.25)
        k("RAlt", 10, 5.5, 1.25, label="Alt"); k("RWin", 11.25, 5.5, 1.25, label="Win"); k("Menu", 12.5, 5.5, 1.25); k("RCtrl", 13.75, 5.5, 1.25, label="Ctrl")
        k("Left", 15.5, 5.5, label="←"); k("Down", 16.5, 5.5, label="↓"); k("Right", 17.5, 5.5, label="→")
        k("Num0", 19, 5.5, 2, label="0"); k("Num.", 21, 5.5, label=".")
        for i, (nm, lb) in enumerate([("Prev", "⏮"), ("Play/Pause", "⏯"), ("Next", "⏭"), ("Stop", "⏹"), ("Vol-", "Vol−"), ("Vol+", "Vol+"), ("Mute", "Mute")]):
            k(nm, i * 1.5, 7.3, 1.4, label=lb)
        for i in range(12): k(f"F{i+13}", i, 8.4)
        return L

    def open_key_picker(on_pick):
        top = tk.Toplevel(ui_root)
        top.title(tr("Choose key"))
        top.configure(bg="#202020")
        top.attributes("-topmost", True)
        top.resizable(False, False)
        U = 36
        W, H = int(23.2 * U) + 30, int(9.6 * U) + 110
        sw, sh = ui_root.winfo_screenwidth(), ui_root.winfo_screenheight()
        top.geometry(f"{W}x{H}+{max(0, (sw - W) // 2)}+{max(0, (sh - H) // 2)}")
        tk.Label(top, text=tr("Press a key to add it to the combination"), fg="#e8e8e8", bg="#202020", font=("Segoe UI", 11)).pack(pady=(12, 6))
        area = tk.Frame(top, bg="#202020")
        area.pack(padx=15, pady=5, fill=tk.BOTH, expand=True)
        def choose(name):
            top.destroy()
            on_pick(name)
        for name, label, x, y, w, h in _hk_layout():
            b = RoundBtn(area, text=label, bg="#2d2d2d", fg="#ffffff", activebackground="#1db954", activeforeground="#000000", font=("Segoe UI", 9), borderwidth=0, cursor="hand2", command=lambda n=name: choose(n))
            b.place(x=int(x * U), y=int(y * U), width=int(w * U) - 3, height=int(h * U) - 3)
            b.bind("<Enter>", lambda e, b=b: b.config(bg="#3a3a3a"))
            b.bind("<Leave>", lambda e, b=b: b.config(bg="#2d2d2d"))
        RoundBtn(top, text=tr("Cancel"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=top.destroy).pack(pady=(0, 12), ipadx=24, ipady=4)

    def send_hotkey(keys):
        seq = [HK_VK[k] for k in keys if k in HK_VK]
        if not seq: return
        u = ctypes.windll.user32
        def ev(vk, ext, up):
            u.keybd_event(vk, u.MapVirtualKeyW(vk, 0), (1 if ext else 0) | (2 if up else 0), 0)
        for vk, ext in seq:
            ev(vk, ext, False); time.sleep(0.012)
        time.sleep(0.03)
        for vk, ext in reversed(seq):
            ev(vk, ext, True); time.sleep(0.012)
        show_osd("⌨ " + " + ".join(keys))

    # ================= ПРИЦЕЛ КАК ФУНКЦИЯ КНОПКИ =================
    _cu = ctypes.WinDLL("user32")
    _cg = ctypes.WinDLL("gdi32")
    class _BMIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD), ("biSizeImage", wintypes.DWORD),
                    ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]
    class _BLEND(ctypes.Structure):
        _fields_ = [("BlendOp", ctypes.c_ubyte), ("BlendFlags", ctypes.c_ubyte), ("SourceConstantAlpha", ctypes.c_ubyte), ("AlphaFormat", ctypes.c_ubyte)]
    class _MONINFO(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
    _H = wintypes.HANDLE
    _cu.GetDC.argtypes = [_H]; _cu.GetDC.restype = _H
    _cu.ReleaseDC.argtypes = [_H, _H]
    _cu.GetParent.argtypes = [_H]; _cu.GetParent.restype = _H
    _cu.GetWindowLongW.argtypes = [_H, ctypes.c_int]; _cu.GetWindowLongW.restype = ctypes.c_long
    _cu.SetWindowLongW.argtypes = [_H, ctypes.c_int, ctypes.c_long]; _cu.SetWindowLongW.restype = ctypes.c_long
    _cu.GetForegroundWindow.restype = _H
    _cu.MonitorFromWindow.argtypes = [_H, wintypes.DWORD]; _cu.MonitorFromWindow.restype = _H
    _cu.GetMonitorInfoW.argtypes = [_H, ctypes.POINTER(_MONINFO)]
    _cu.UpdateLayeredWindow.argtypes = [_H, _H, ctypes.POINTER(wintypes.POINT), ctypes.POINTER(wintypes.SIZE), _H, ctypes.POINTER(wintypes.POINT), wintypes.DWORD, ctypes.POINTER(_BLEND), wintypes.DWORD]
    _cu.UpdateLayeredWindow.restype = wintypes.BOOL
    _cg.CreateCompatibleDC.argtypes = [_H]; _cg.CreateCompatibleDC.restype = _H
    _cg.CreateDIBSection.argtypes = [_H, ctypes.c_void_p, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p), _H, wintypes.DWORD]; _cg.CreateDIBSection.restype = _H
    _cg.SelectObject.argtypes = [_H, _H]; _cg.SelectObject.restype = _H
    _cg.DeleteObject.argtypes = [_H]
    _cg.DeleteDC.argtypes = [_H]

    crosshair_state = {"win": None, "name": None}
    ch_idx = {}

    def _foreground_monitor_rect():
        try:
            hmon = _cu.MonitorFromWindow(_cu.GetForegroundWindow(), 1)
            mi = _MONINFO(); mi.cbSize = ctypes.sizeof(_MONINFO)
            if hmon and _cu.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                r = mi.rcMonitor
                return r.left, r.top, r.right, r.bottom
        except Exception: pass
        return 0, 0, ui_root.winfo_screenwidth(), ui_root.winfo_screenheight()

    def _layered_present(hwnd, img, x, y, alpha=255):
        # Окно с попиксельной прозрачностью (честная альфа, без colorkey-каймы)
        w, h = img.size
        hdc_screen = _cu.GetDC(None)
        hdc_mem = _cg.CreateCompatibleDC(hdc_screen)
        bmih = _BMIH(); bmih.biSize = ctypes.sizeof(_BMIH); bmih.biWidth = w; bmih.biHeight = -h
        bmih.biPlanes = 1; bmih.biBitCount = 32; bmih.biCompression = 0
        bits = ctypes.c_void_p()
        hbmp = _cg.CreateDIBSection(hdc_screen, ctypes.byref(bmih), 0, ctypes.byref(bits), None, 0)
        ok = False
        try:
            if not hbmp or not bits.value: raise OSError("DIB")
            data = img.convert("RGBa").tobytes("raw", "BGRa")
            ctypes.memmove(bits.value, data, len(data))
            old = _cg.SelectObject(hdc_mem, hbmp)
            pt_dst = wintypes.POINT(int(x), int(y)); sz = wintypes.SIZE(w, h); pt_src = wintypes.POINT(0, 0)
            blend = _BLEND(0, 0, int(alpha), 1)
            ok = bool(_cu.UpdateLayeredWindow(hwnd, hdc_screen, ctypes.byref(pt_dst), ctypes.byref(sz), hdc_mem, ctypes.byref(pt_src), 0, ctypes.byref(blend), 2))
            _cg.SelectObject(hdc_mem, old)
        finally:
            if hbmp: _cg.DeleteObject(hbmp)
            _cg.DeleteDC(hdc_mem)
            _cu.ReleaseDC(None, hdc_screen)
        return ok

    def hide_crosshair():
        w = crosshair_state.get("win")
        if w is not None:
            try: w.destroy()
            except Exception: pass
        crosshair_state["win"] = None
        crosshair_state["name"] = None

    def show_crosshair(name):
        params = MACRO_CONFIG.get("Crosshairs", {}).get(name)
        if not params:
            show_osd(tr("Crosshair not found"))
            return False
        hide_crosshair()
        base = dict(DEFAULT_CONFIG["Crosshairs"]["Default"]); base.update(params)
        SZ = 200
        img = render_crosshair_image(base, size=SZ)
        l, t, r, b = _foreground_monitor_rect()
        x, y = l + (r - l - SZ) // 2, t + (b - t - SZ) // 2
        win = tk.Toplevel(ui_root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry(f"{SZ}x{SZ}+{x}+{y}")
        win.update_idletasks()
        crosshair_state["win"] = win
        crosshair_state["name"] = name
        try:
            hwnd = _cu.GetParent(win.winfo_id()) or win.winfo_id()
            ex = _cu.GetWindowLongW(hwnd, -20)
            # LAYERED | TRANSPARENT (клики насквозь) | TOOLWINDOW | NOACTIVATE
            _cu.SetWindowLongW(hwnd, -20, ex | 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000)
            if not _layered_present(hwnd, img, x, y): raise OSError("UpdateLayeredWindow")
        except Exception:
            try:
                key = "#010203"
                win.configure(bg=key)
                win.wm_attributes("-transparentcolor", key)
                comp = Image.new("RGBA", img.size, (1, 2, 3, 255)); comp.alpha_composite(img)
                photo = ImageTk.PhotoImage(comp.convert("RGB"))
                lbl = tk.Label(win, image=photo, bg=key, borderwidth=0)
                lbl.image = photo
                lbl.pack()
            except Exception: pass
        return True

    def crosshair_action(sc, cfg, is_second):
        cr = cfg.get("Crosshair") or {}
        presets = MACRO_CONFIG.get("Crosshairs", {})
        if cr.get("mode") == "smart":
            names = [n for n in cr.get("list", []) if n in presets]
            if not names:
                show_osd(tr("Crosshair: list is empty"))
                return
            idx = ch_idx.get(sc, 0) % len(names)
            if is_second:
                if crosshair_state["win"] is not None:
                    hide_crosshair(); show_osd(tr("Crosshair OFF"))
                elif show_crosshair(names[idx]):
                    ch_idx[sc] = idx; show_osd(tr("Crosshair: {}").format(names[idx]))
            else:
                idx = (idx + 1) % len(names)
                ch_idx[sc] = idx
                if crosshair_state["win"] is not None: show_crosshair(names[idx])
                show_osd(tr("Crosshair: {}").format(names[idx]))
        else:
            nm = cr.get("name") or next(iter(presets), "")
            if crosshair_state["win"] is not None and crosshair_state["name"] == nm:
                hide_crosshair(); show_osd(tr("Crosshair OFF"))
            elif show_crosshair(nm):
                show_osd(tr("Crosshair: {}").format(nm))

    def set_extended_keyboard(on):
        MACRO_CONFIG["AppSettings"]["extended_kb"] = bool(on)
        save_config()
        update_allowed_keys()
        try: draw_numpad()
        except Exception: _runlog("draw_numpad after extended toggle:\n" + traceback.format_exc())
        # settings panel stays over the numpad, which did not move on screen
        try:
            if settings_bg_frame.winfo_ismapped(): settings_bg_frame.place_configure(x=ext_offset() + 14)
        except Exception: pass
        try: build_settings_screen()
        except Exception: pass

    def show_extended_warning():
        win = tk.Toplevel(ui_root)
        win.title("Extended keyboard")
        win.configure(bg="#111111")
        win.transient(ui_root)
        win.resizable(False, False)
        decided = {"v": False}
        def cancel():
            if decided["v"]: return
            decided["v"] = True
            try: win.destroy()
            except Exception: pass
            try: build_settings_screen()   # switch back to off
            except Exception: pass
        def enable():
            decided["v"] = True
            try: win.destroy()
            except Exception: pass
            set_extended_keyboard(True)
        win.protocol("WM_DELETE_WINDOW", cancel)
        # buttons first, at the bottom: they always stay visible, whatever the text height or DPI
        btn_row = tk.Frame(win, bg="#111111")
        btn_row.pack(side=tk.BOTTOM, fill=tk.X, padx=24, pady=(10, 18))
        RoundBtn(btn_row, text=tr("Cancel"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10, "bold"), borderwidth=0, cursor="hand2", command=cancel).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=6)
        RoundBtn(btn_row, text=tr("Enable anyway"), bg="#c62828", fg="#ffffff", font=("Segoe UI", 10, "bold"), borderwidth=0, cursor="hand2", command=enable).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0), ipady=6)
        tk.Label(win, text="⚠  " + tr("Experimental feature"), fg="#ff5a4f", bg="#111111", font=("Segoe UI", 15, "bold")).pack(anchor="w", padx=24, pady=(20, 8))
        tk.Label(win, text=tr("Extended keyboard is a very experimental feature. It will most likely not get much support, and it may change or be removed.\n\n"
                              "It lets numbinder take over the F-keys, arrows, Insert…Page Down, Right Alt and Right Ctrl. "
                              "A key you bind stops working normally in every program, which can seriously affect normal use of your computer.\n\n"
                              "Using this feature is not recommended."),
                 fg="#dddddd", bg="#111111", font=("Segoe UI", 10), wraplength=390, justify=tk.LEFT).pack(anchor="w", padx=24)
        try: win.grab_set()
        except Exception: pass

    def show_main_screen():
        ui_root.osd_preview_mode = False
        if 'start_fade' in globals(): globals()['start_fade'](0.95)
        config_bg_frame.place_forget()
        settings_bg_frame.place_forget()
        crosshair_bg_frame.place_forget()

    def show_settings_screen():
        build_settings_screen()
        config_bg_frame.place_forget()
        crosshair_bg_frame.place_forget()
        dev = MACRO_CONFIG.get("DevSettings", {})
        win_w, win_h = WIN_W, WIN_H
        pad = 14
        settings_bg_frame.update_idletasks()
        _slide_in_up(settings_bg_frame, ext_offset() + pad, win_w-pad*2, win_h-pad*2, pad, -win_h)   # сверху вниз

    _slide_token = {"n": 0}
    def _slide_in_up(frame, x, w, h, y_final, from_y, dur_ms=320):
        """The window slides in on the same exponential curve as the popup."""
        _slide_token["n"] += 1
        tok = _slide_token["n"]
        t0 = time.perf_counter()
        frame.place(x=x, y=from_y, width=w, height=h)
        frame.lift()
        def tick():
            if tok != _slide_token["n"] or not frame.winfo_manager(): return
            t = min(1.0, (time.perf_counter() - t0) * 1000.0 / dur_ms)
            f = (1 - 2 ** (-10 * t)) / _EXP_LIM
            t_frame = time.perf_counter()
            frame.place_configure(y=from_y + (y_final - from_y) * f)
            if t < 1.0:
                spent = (time.perf_counter() - t_frame) * 1000.0
                ui_root.after(max(1, int(16.6 - spent)), tick)
        tick()

    def open_config_screen(sc):
        global current_edit_sc
        current_edit_sc = str(sc)
        cfg = MACRO_CONFIG.get(current_edit_sc, MACRO_TEMPLATE.copy())
        
        key_name = SC_NAMES.get(current_edit_sc, f"NUM_{current_edit_sc}")
        
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        config_canvas.config(bg=_bg)
        config_content.config(bg=_bg)
        config_title.config(text=tr("Configure {}").format(key_name), bg=_bg)
        lbl_overlay_tip.config(bg=_bg)
        lbl_ch_tip.config(bg=_bg)
        
        for r in [row_type, row_lang, row_path, row_proc, row_act, row_sec, row_admin, row_voldir, row_volpair, row_voltarget, row_volmode, row_volsteps, row_icon_path, row_icon_color, row_ch_mode, row_ch_name, config_bottom_fr]:
            r.config(bg=_bg)
            for child in r.winfo_children():
                if isinstance(child, tk.Frame): child.config(bg=_bg)
                if isinstance(child, tk.Label): child.config(bg=_bg)
        sound_container.config(bg=_bg)
        for child in sound_container.winfo_children():
            if isinstance(child, tk.Frame): child.config(bg=_bg)
            if isinstance(child, tk.Label): child.config(bg=_bg)
            for c2 in child.winfo_children():
                if isinstance(c2, tk.Label): c2.config(bg=_bg)
        
        var_type.set(type_to_label(cfg.get("Type", "none")))
        var_lang.set(cfg.get("Language", "ENG") if cfg.get("Language") != "-1" else "ENG")
        var_path.set(cfg.get("Path", "") if cfg.get("Path") != "-1" else "")
        var_proc.set(cfg.get("ProcessName", "spotify.exe") if cfg.get("ProcessName") != "-1" else "spotify.exe")
        var_act.set(str(cfg.get("ActionTime", 0)))
        var_sec.set(str(cfg.get("SecondActionTime", -1)) if cfg.get("SecondActionTime") != -1 else "")
        var_clean_keep.set(cfg.get("CleanKeep", ""))
        var_media.set(next((m[1] for m in MEDIA_KEYS if m[0] == cfg.get("MediaKey", "playpause")), MEDIA_KEYS[0][1]))
        _set_action_rows(_get_actions(cfg))
        var_mic_mode.set(next((m[1] for m in MIC_MODES if m[0] == cfg.get("MicMode", "toggle")), MIC_MODES[0][1]))
        var_admin_bool.set(True if cfg.get("AdminRights") == 1 else False)
        var_vol_dir.set("Up (+)" if cfg.get("VolumeDirection", 1) == 1 else "Down (-)")
        var_vol_mode.set(_VM_STEPS if cfg.get("VolumeMode") == "steps" else _VM_SLIDER)
        var_vol_steps.set(", ".join(str(x) for x in cfg.get("VolumeSteps", [0, 50, 100])))
        var_vol_target.set(next((k for k, v in _VT_CODES.items() if v == cfg.get("VolumeTarget", "process")), _VT_PROC))
        var_icon_path.set(cfg.get("IconPath", ""))
        var_icon_color.set(cfg.get("IconColor", "#ffffff"))
        row_icon_color.winfo_children()[1].config(bg=var_icon_color.get(), text=var_icon_color.get())
        
        aud = cfg.get("Audio", MACRO_TEMPLATE["Audio"].copy())
        for key, var in audio_vars.items(): var.set(aud.get(key, MACRO_TEMPLATE["Audio"][key]))

        cr = cfg.get("Crosshair") or {}
        ch_names = list(MACRO_CONFIG.get("Crosshairs", {}).keys())
        var_ch_mode.set(_CH_MODE_SMART if cr.get("mode") == "smart" else _CH_MODE_TOGGLE)
        row_ch_name.winfo_children()[1].configure(values=ch_names)
        var_ch_name.set(cr.get("name") if cr.get("name") in ch_names else (ch_names[0] if ch_names else ""))
        ch_sel[:] = [n for n in cr.get("list", []) if n in ch_names]
        hotkey_list[:] = [str(k) for k in cfg.get("Hotkey", [])]
        
        opts = [tr("None")] + [SC_NAMES[k] for k in SC_NAMES if k != current_edit_sc and k not in LOCKED_SC and k in allowed_keys]
        row_volpair.winfo_children()[1].configure(values=opts)
        _pair = str(cfg.get("Pair", "-1"))
        var_vol_pair.set(SC_NAMES[_pair] if (cfg.get("Type") == "volume" and _pair in SC_NAMES and _pair != current_edit_sc) else tr("None"))

        refresh_config_ui()
        settings_bg_frame.place_forget()
        crosshair_bg_frame.place_forget()
        
        dev = MACRO_CONFIG.get("DevSettings", {})
        win_w, win_h = WIN_W, WIN_H
        pad = 14
        
        config_bg_frame.update_idletasks()   # сначала раскладка и отрисовка, потом показ
        _slide_in_up(config_bg_frame, ext_offset() + pad, win_w-pad*2, win_h-pad*2, pad, win_h)

    draw_numpad()

    # ================= ОСНОВНЫЕ OSD ФУНКЦИИ =================
    # Попап рисуется целиком через PIL и выводится окном с попиксельной
    # прозрачностью (UpdateLayeredWindow): скругление 52px, заливка 64%,
    # обводка, свечение текста и анимация масштаба — всё без Tk-виджетов.
    OSD_FILL = (32, 32, 32)
    OSD_FILL_ALPHA = int(round(0.64 * 255))
    OSD_BORDER = (199, 199, 199)
    OSD_RADIUS, OSD_BORDER_W = 52, 3
    OSD_ANIM_MS, OSD_ANIM_UP_MS = 462, 268

    osd_win = tk.Toplevel(ui_root)
    osd_win.overrideredirect(True)
    osd_win.attributes("-topmost", True)
    osd_win.geometry("1x1+0+0")
    osd_win.withdraw()

    osd_icon_cache, osd_font_cache = {}, {}
    hide_timer = [None]
    osd_state = {"base": None, "cx": 0, "cy": 0, "visible": False, "alpha": 1.0, "t0": 0.0, "anim": None}

    def _osd_font(px, kind="text"):
        px = max(8, int(px))
        key = (px, kind)
        if key in osd_font_cache: return osd_font_cache[key]
        names = {"text": ("segoeuib.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf"),
                 "sym": ("seguisym.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"),
                 "emoji": ("seguiemj.ttf", "seguisym.ttf", "DejaVuSans-Bold.ttf")}[kind]
        font = None
        for nm in names:
            try:
                font = ImageFont.truetype(nm, px); break
            except Exception: continue
        if font is None: font = ImageFont.load_default()
        osd_font_cache[key] = font
        return font

    def _osd_runs(text, px):
        # Segoe UI не содержит стрелок/эмодзи — рисуем такие символы запасным шрифтом
        runs = []
        for ch in text:
            o = ord(ch)
            if o in (0xFE0F, 0x200D): continue
            kind = "emoji" if o >= 0x1F000 else ("sym" if 0x2190 <= o <= 0x2BFF else "text")
            if runs and runs[-1][0] == kind: runs[-1][1].append(ch)
            else: runs.append((kind, [ch]))
        return [("".join(chs), _osd_font(px, kind)) for kind, chs in runs]

    def _osd_text_w(draw, text, px):
        return sum(draw.textlength(s, font=f) for s, f in _osd_runs(text, px))

    def _osd_wrap(draw, text, px, max_w):
        lines = []
        for para in str(text).split("\n"):
            cur = ""
            for word in para.split(" "):
                trial = (cur + " " + word).strip()
                if not cur or _osd_text_w(draw, trial, px) <= max_w: cur = trial
                else:
                    lines.append(cur); cur = word
            lines.append(cur)
        out = []
        for ln in lines:
            while len(ln) > 1 and _osd_text_w(draw, ln, px) > max_w:
                k = len(ln)
                while k > 1 and _osd_text_w(draw, ln[:k], px) > max_w: k -= 1
                out.append(ln[:k]); ln = ln[k:]
            out.append(ln)
        return out or [""]

    def _osd_draw_text(draw, x, y, text, px, fill):
        for s, f in _osd_runs(text, px):
            draw.text((x, y), s, font=f, fill=fill)
            x += draw.textlength(s, font=f)

    def _osd_icon(path, box, color):
        key = (path, box, color)
        if key not in osd_icon_cache:
            img = Image.open(path).convert("RGBA")
            img.thumbnail((box, box), Image.Resampling.LANCZOS)
            r, g, b, a = img.split()
            tr, tg, tb = color
            osd_icon_cache[key] = Image.merge("RGBA", (r.point(lambda i: i * tr // 255), g.point(lambda i: i * tg // 255), b.point(lambda i: i * tb // 255), a))
        return osd_icon_cache[key]

    def _osd_rgb(key, default):
        try:
            h = str(MACRO_CONFIG["AppSettings"].get(key, default)).lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        except Exception:
            h = default.lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

    def render_osd_image(msg, icon_path, is_close, prog, scale):
        S = max(0.3, float(scale))
        px = int(24 * S)
        line_h = int(px * 1.3)
        icon_box = int(64 * S)
        bar_h = max(4, int(8 * S))
        gap1, gap2 = int(16 * S), int(18 * S)
        text_col = (204, 41, 41) if is_close else _osd_rgb("osd_text_color", "#cccccc")
        glow_col = (255, 90, 90) if is_close else _osd_rgb("osd_glow_color", "#ebebeb")

        meas = ImageDraw.Draw(Image.new("L", (1, 1)))
        lines = _osd_wrap(meas, msg, px, int(320 * S))
        text_w = int(max(_osd_text_w(meas, ln, px) for ln in lines))
        has_icon = bool(icon_path and os.path.exists(icon_path))
        bar_w = max(text_w, int(140 * S)) if prog is not None else 0

        # размер окна = размер содержимого x 1.66 по обеим осям; не меньше диаметра
        # скругления (иначе радиус 52 не помещается) и не выше, чем шире
        content_w = max(text_w, icon_box if has_icon else 0, bar_w)
        content_h = line_h * len(lines)
        if has_icon: content_h += icon_box + gap1
        if prog is not None: content_h += gap2 + bar_h
        min_side = int(2 * OSD_RADIUS * S)
        H = int(max(content_h * 1.66, min_side))
        W = int(max(content_w * 1.66, min_side, H))

        # панель: скруглённая заливка 64% + непрозрачная обводка, маски в 4x для сглаживания
        k = 4
        r, bw = int(OSD_RADIUS * S * k), max(1, int(OSD_BORDER_W * S * k))
        outer = Image.new("L", (W * k, H * k), 0)
        ImageDraw.Draw(outer).rounded_rectangle([0, 0, W * k - 1, H * k - 1], radius=r, fill=255)
        inner = Image.new("L", (W * k, H * k), 0)
        ImageDraw.Draw(inner).rounded_rectangle([bw, bw, W * k - 1 - bw, H * k - 1 - bw], radius=max(1, r - bw), fill=255)
        outer = outer.resize((W, H), Image.Resampling.LANCZOS)
        inner = inner.resize((W, H), Image.Resampling.LANCZOS)
        border = Image.new("RGBA", (W, H), _osd_rgb("osd_border_color", "#c7c7c7") + (255,))
        border.putalpha(ImageChops.subtract(outer, inner))
        fill = Image.new("RGBA", (W, H), _osd_rgb("osd_bg_color", "#202020") + (255,))
        fill.putalpha(inner.point(lambda v: v * OSD_FILL_ALPHA // 255))
        img = Image.alpha_composite(border, fill)

        content = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        cd = ImageDraw.Draw(content)
        y = (H - content_h) // 2
        if has_icon:
            if is_close:
                cd.ellipse([(W - icon_box) // 2, y, (W + icon_box) // 2, y + icon_box], fill=(204, 41, 41, 255))
                ic = _osd_icon(icon_path, int(icon_box * 0.58), (255, 255, 255))
            else:
                ic = _osd_icon(icon_path, icon_box, text_col)
            content.alpha_composite(ic, ((W - ic.width) // 2, y + (icon_box - ic.height) // 2))
            y += icon_box + gap1

        text_y0 = y
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow)
        for i, ln in enumerate(lines):
            lw = _osd_text_w(meas, ln, px)
            _osd_draw_text(gd, (W - lw) / 2, text_y0 + i * line_h, ln, px, glow_col + (255,))
            _osd_draw_text(cd, (W - lw) / 2, text_y0 + i * line_h, ln, px, text_col + (255,))
        glow = glow.filter(ImageFilter.GaussianBlur(radius=max(2, 7 * S)))
        glow.putalpha(glow.getchannel("A").point(lambda v: min(255, int(v * 1.9))))
        y = text_y0 + line_h * len(lines)

        if prog is not None:
            y += gap2
            bw_total = bar_w; bx = (W - bw_total) // 2
            cd.rounded_rectangle([bx, y, bx + bw_total, y + bar_h], radius=bar_h // 2, fill=(51, 51, 51, 255))
            if prog > 0:
                cd.rounded_rectangle([bx, y, bx + max(bar_h, int(bw_total * min(1.0, prog))), y + bar_h], radius=bar_h // 2, fill=(29, 185, 84, 255))

        # порядок: панель -> свечение -> иконка/полоса/текст (внутри content)
        img = Image.alpha_composite(img, glow)
        img = Image.alpha_composite(img, content)
        return img

    def _osd_scale_at(ms):
        # 0% -> 110% за 268 мс, затем 110% -> 100% за 194 мс; оба участка экспоненциальные
        lim = 1 - 2 ** -10
        if ms >= OSD_ANIM_MS: return 1.0
        if ms < OSD_ANIM_UP_MS:
            t = ms / OSD_ANIM_UP_MS
            return 1.1 * (1 - 2 ** (-10 * t)) / lim
        t = (ms - OSD_ANIM_UP_MS) / (OSD_ANIM_MS - OSD_ANIM_UP_MS)
        return 1.0 + 0.1 * (2 ** (-10 * t) - 2 ** -10) / lim

    def _osd_present(frame, alpha=1.0):
        try:
            hwnd = _cu.GetParent(osd_win.winfo_id()) or osd_win.winfo_id()
            ex = _cu.GetWindowLongW(hwnd, -20)
            want = ex | 0x00080000 | 0x00000020 | 0x00000080 | 0x08000000
            if want != ex: _cu.SetWindowLongW(hwnd, -20, want)
            w, h = frame.size
            _layered_present(hwnd, frame, osd_state["cx"] - w // 2, osd_state["cy"] - h // 2, int(max(0.0, min(1.0, alpha)) * 255))
        except Exception:
            pass

    def _osd_anim_tick():
        osd_state["anim"] = None
        base = osd_state["base"]
        if base is None or not osd_state["visible"]: return
        ms = (time.perf_counter() - osd_state["t0"]) * 1000.0
        if ms >= OSD_ANIM_MS:
            _osd_present(base, osd_state["alpha"])
            return
        s = _osd_scale_at(ms)
        if s > 0.02:
            frame = base.resize((max(1, int(base.width * s)), max(1, int(base.height * s))), Image.Resampling.BICUBIC)
        else:
            frame = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        _osd_present(frame, osd_state["alpha"])
        osd_state["anim"] = ui_root.after(15, _osd_anim_tick)

    def _osd_show(img, auto_hide=True):
        app = MACRO_CONFIG["AppSettings"]
        sw, sh = ui_root.winfo_screenwidth(), ui_root.winfo_screenheight()
        w, h = img.size
        x = int((sw - w) * (app.get("osd_x", 50) / 100.0))
        y = int((sh - h) * (app.get("osd_y", 5) / 100.0))
        osd_state.update(base=img, cx=x + w // 2, cy=y + h // 2, alpha=1.0)
        if hide_timer[0]:
            ui_root.after_cancel(hide_timer[0]); hide_timer[0] = None
        if not osd_state["visible"]:
            osd_state["visible"] = True
            osd_win.deiconify()
            osd_win.update_idletasks()
            osd_state["t0"] = time.perf_counter()
            if osd_state["anim"]: ui_root.after_cancel(osd_state["anim"])
            _osd_anim_tick()
        elif osd_state["anim"] is None:
            _osd_present(img, 1.0)
        if auto_hide: hide_timer[0] = ui_root.after(2000, start_fade)

    def start_fade(alpha=0.95):
        if not osd_state["visible"]: return
        if alpha > 0:
            alpha -= 0.07
            osd_state["alpha"] = max(0.0, alpha)
            if osd_state["anim"] is None and osd_state["base"] is not None:
                _osd_present(osd_state["base"], osd_state["alpha"])
            hide_timer[0] = ui_root.after(30, start_fade, alpha)
        else:
            osd_state["visible"] = False
            osd_state["alpha"] = 0.0
            try: osd_win.withdraw()
            except Exception: pass

    def force_osd_preview():
        try:
            scale = MACRO_CONFIG["AppSettings"].get("osd_scale", 1.0)
            _osd_show(render_osd_image(tr("PREVIEW 65%"), None, False, 0.65, scale), auto_hide=False)
        except Exception:
            traceback.print_exc()

    def process_osd_queue():
        try:
            last = None
            try:
                while True:
                    data = osd_queue.get_nowait()
                    if getattr(ui_root, "osd_preview_mode", False): continue
                    last = data
            except queue.Empty: pass
            if last is not None:
                scale = MACRO_CONFIG["AppSettings"].get("osd_scale", 1.0)
                img = render_osd_image(last["msg"], last["icon"], last["is_close"], last["progress"], scale)
                _osd_show(img)
        except Exception:
            traceback.print_exc()
        finally:
            ui_root.after(50, process_osd_queue)

    ui_root.after(50, process_osd_queue)

    def show_osd(message, icon=None, is_close=False, progress=None):
        osd_queue.put({"msg": message, "icon": icon, "is_close": is_close, "progress": progress})

    # ================= ЗВУК ПРИ СРАБАТЫВАНИИ КНОПКИ =================
    # Файл action1.mp4 (или .mp3/.wav/.m4a) лежит рядом со скриптом. Играет через
    # системный MCI; каждое срабатывание берёт свободный "channel" из пула, поэтому
    # новый звук не обрывает предыдущий. Если MCI не умеет такой файл — запасной
    # плеер на PowerShell (тоже с наложением). Громкость — настройка приложения.
    _snd = {"q": queue.Queue(), "thread": None}

    def _find_action_sound():
        for ext in (".mp4", ".mp3", ".wav", ".m4a"):
            p = asset("action1" + ext)
            if os.path.exists(p): return p
        return None

    def _sound_worker():
        winmm = ctypes.WinDLL("winmm")
        winmm.mciSendStringW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.UINT, wintypes.HANDLE]
        winmm.mciSendStringW.restype = wintypes.DWORD
        def mci(cmd):
            buf = ctypes.create_unicode_buffer(256)
            err = winmm.mciSendStringW(cmd, buf, 255, None)
            return err, buf.value
        st = {"path": None, "mci_ok": None, "pool": [], "n": 0, "ps": None}

        def reset(path):
            for a in st["pool"]: mci(f"close {a}")
            if st["ps"] is not None:
                try: st["ps"].kill()
                except Exception: pass
            st.update(path=path, mci_ok=None, pool=[], ps=None)

        def open_alias(path):
            st["n"] += 1
            a = f"act{st['n']}"
            if mci(f'open "{path}" type mpegvideo alias {a}')[0] == 0 or mci(f'open "{path}" alias {a}')[0] == 0:
                st["pool"].append(a)
                return a
            return None

        def pick_alias(path):
            for a in st["pool"]:
                err, mode = mci(f"status {a} mode")
                if err == 0 and mode == "stopped": return a
            if len(st["pool"]) < 8: return open_alias(path)
            a = st["pool"].pop(0)          # все заняты — перезапускаем самый старый
            st["pool"].append(a)
            return a

        while True:
            vol = _snd["q"].get()
            try:
                p = _find_action_sound()
                if not p:
                    _runlog(f"SOUND: action1.mp4 not found in {PATH_ASSETS}")
                    continue
                if p != st["path"]: reset(p)
                if st["mci_ok"] is not False:
                    a = pick_alias(p)
                    if a:
                        st["mci_ok"] = True
                        mci(f"setaudio {a} volume to {int(vol) * 10}")
                        mci(f"seek {a} to start")
                        if mci(f"play {a}")[0] == 0: continue
                    elif not st["pool"]:
                        st["mci_ok"] = False
                ps = st["ps"]
                if ps is None or ps.poll() is not None:
                    script = ("Add-Type -AssemblyName PresentationCore; $ps = New-Object System.Collections.ArrayList; "
                              "while ($l = [Console]::In.ReadLine()) { "
                              "foreach ($q in @($ps)) { if ($q.NaturalDuration.HasTimeSpan -and $q.Position -ge $q.NaturalDuration.TimeSpan) { $q.Close(); $ps.Remove($q) } } "
                              "$p = New-Object System.Windows.Media.MediaPlayer; $p.Volume = [double]$l; "
                              "$p.Open([Uri]'__PATH__'); $p.Play(); [void]$ps.Add($p) }").replace("__PATH__", p.replace("'", "''"))
                    ps = subprocess.Popen(["powershell", "-NoProfile", "-STA", "-WindowStyle", "Hidden", "-Command", script],
                                          stdin=subprocess.PIPE, creationflags=0x08000000, text=True)
                    st["ps"] = ps
                ps.stdin.write(f"{int(vol) / 100.0:.2f}\n"); ps.stdin.flush()
            except Exception:
                traceback.print_exc()

    def play_action_sound(force=False):
        app = MACRO_CONFIG.get("AppSettings", {})
        if not force and not app.get("action_sound", True): return
        if _snd["thread"] is None:
            _snd["thread"] = threading.Thread(target=_sound_worker, daemon=True)
            _snd["thread"].start()
        _snd["q"].put(max(0, min(100, int(app.get("action_sound_volume", 100)))))

    # --- Трей ---
    def create_tray_image():
        try:
            img = Image.open(PATH_LOGO).convert("RGBA")
            img = img.resize((64, 64), Image.Resampling.LANCZOS)
            if not macro_enabled: img = ImageOps.grayscale(img).convert("RGBA")
            return img
        except:
            img = Image.new('RGBA', (64, 64), (0, 0, 0, 0))
            ImageDraw.Draw(img).ellipse((16, 16, 48, 48), fill="#1db954" if macro_enabled else "#555555")
            return img

    def tray_show_ui(icon, item): 
        ui_root.after(0, ui_root.deiconify)
        ui_root.after(10, lambda: ui_root.attributes('-topmost', True))
        ui_root.after(100, lambda: [set_appwindow(), ui_root.attributes('-topmost', False), ui_root.focus_force()])

    def tray_quit(icon, item): 
        icon.stop(); os._exit(0)

    menu = pystray.Menu(item(tr('Settings'), tray_show_ui, default=True), item(tr('Exit'), tray_quit))
    tray_icon = pystray.Icon("numbinder", create_tray_image(), "numbinder", menu)
    threading.Thread(target=tray_icon.run, daemon=True).start()

    # ================= ФУНКЦИОНАЛ МАКРОСОВ И ОВЕРЛЕЕВ =================
    vol_audio_cfg = {}
    active_overlays = {}
    
    def refresh_overlay(sc):
        if sc not in active_overlays: return
        win, label = active_overlays[sc]
        cfg = MACRO_CONFIG[sc].get("Overlay", {})
        
        blend = cfg.get("blend", "black")
        bg_color = "#000000"
        if blend == "white": bg_color = "#ffffff"
        elif blend == "magenta": bg_color = "#ff00ff"
        
        win.configure(bg=bg_color)
        win.wm_attributes("-transparentcolor", bg_color)
        label.config(bg=bg_color)
        
        try:
            pil_img = Image.open(cfg["path"]).convert("RGBA")
            
            if cfg.get("fix_alpha", False):
                r, g, b, a = pil_img.split()
                a = a.point(lambda p: 255 if p > 127 else 0)
                pil_img = Image.merge("RGBA", (r, g, b, a))
            
            if cfg.get("x", -1) == -1 or cfg.get("y", -1) == -1:
                sw, sh = ui_root.winfo_screenwidth(), ui_root.winfo_screenheight()
                cfg["x"] = sw // 2 - int(cfg.get("w", 200)) // 2
                cfg["y"] = sh // 2 - int(cfg.get("h", 200)) // 2

            resample_mode = Image.Resampling.LANCZOS if cfg.get("smooth", True) else Image.Resampling.NEAREST
            pil_img = pil_img.resize((int(cfg["w"]), int(cfg["h"])), resample_mode)
            
            bg_rgb = tuple(int(bg_color[i:i+2], 16) for i in (1, 3, 5))
            comp_bg = Image.new("RGBA", pil_img.size, bg_rgb + (255,))
            comp_bg.paste(pil_img, (0, 0), pil_img)
            
            new_img = ImageTk.PhotoImage(comp_bg)
            label.config(image=new_img)
            label.image = new_img
            win.geometry(f"{int(cfg['w'])}x{int(cfg['h'])}+{int(cfg['x'])}+{int(cfg['y'])}")
            win.attributes("-alpha", cfg.get("alpha", 80) / 100.0)
        except Exception as e: pass

    def toggle_overlay(sc, force_show=False):
        if sc in active_overlays and not force_show:
            active_overlays[sc][0].destroy()
            del active_overlays[sc]
            return
        
        if sc in active_overlays and force_show: return
            
        cfg = MACRO_CONFIG[sc].get("Overlay", {})
        if not cfg.get("path") or not os.path.exists(cfg["path"]):
            if not force_show: show_osd(tr("Overlay: no image")); return
            
        win = tk.Toplevel(ui_root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#000000")
        win.wm_attributes("-transparentcolor", "#000000")
        
        label = tk.Label(win, bg="#000000")
        label.pack(fill=tk.BOTH, expand=True)
        
        def start_drag(e):
            if cfg.get("interactive", True): win._mv = (e.x_root - win.winfo_x(), e.y_root - win.winfo_y())
        def do_drag(e):
            off = getattr(win, "_mv", None)
            if cfg.get("interactive", True) and off:
                new_x, new_y = e.x_root - off[0], e.y_root - off[1]
                win.geometry(f"+{new_x}+{new_y}")
                MACRO_CONFIG[sc]["Overlay"]["x"] = new_x
                MACRO_CONFIG[sc]["Overlay"]["y"] = new_y

        label.bind("<ButtonPress-1>", start_drag)
        label.bind("<B1-Motion>", do_drag)
        
        active_overlays[sc] = (win, label)
        
        def apply_style():
            try:
                hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
                style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                if not cfg.get("interactive", True):
                    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00000020)
                else:
                    ctypes.windll.user32.SetWindowLongW(hwnd, -20, style & ~0x00000020)
            except: pass
        win.after(50, apply_style)
        
        refresh_overlay(sc)
        if not force_show: show_osd(tr("Overlay ON"))

    def open_overlay_settings(sc):
        cfg = MACRO_CONFIG[sc].setdefault("Overlay", MACRO_TEMPLATE["Overlay"].copy())
        
        top = tk.Toplevel(ui_root)
        top.title(tr("Overlay studio"))
        top.geometry("380x580")
        top.attributes("-topmost", True)
        top.configure(bg="#1e1e1e")
        
        tk.Label(top, text=tr("OVERLAY STUDIO"), fg="#1db954", bg="#1e1e1e", font=("Consolas", 14, "bold")).pack(pady=(15, 10))
        
        toggle_overlay(sc, force_show=True)
        
        def redraw(*args):
            if sc in active_overlays: refresh_overlay(sc)
            
        fr_path = tk.Frame(top, bg="#1e1e1e"); fr_path.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(fr_path, text=tr("Image:"), fg="#ccc", bg="#1e1e1e").pack(side=tk.LEFT)
        btn_path = RoundBtn(fr_path, text=tr("Browse..."), bg="#333", fg="#fff", bd=0, cursor="hand2")
        btn_path.pack(side=tk.RIGHT)
        lbl_path = tk.Label(top, text=os.path.basename(cfg["path"]) or tr("Not selected"), fg="#888", bg="#1e1e1e")
        lbl_path.pack(padx=20)
        
        def pick_img():
            p = filedialog.askopenfilename(parent=top, filetypes=[("Images", "*.png *.jpg *.jpeg *.bmp")])
            if p:
                cfg["path"] = p
                lbl_path.config(text=os.path.basename(p))
                try:
                    im = Image.open(p)
                    cfg["w"], cfg["h"] = im.width, im.height
                    var_w.set(im.width); var_h.set(im.height)
                    orig_asp[0] = im.width / im.height
                    
                    sw, sh = ui_root.winfo_screenwidth(), ui_root.winfo_screenheight()
                    cfg["x"] = sw // 2 - im.width // 2
                    cfg["y"] = sh // 2 - im.height // 2
                    var_x.set(cfg["x"]); var_y.set(cfg["y"])
                except: pass
                redraw()
        btn_path.config(command=pick_img)
        
        def add_slider(label, key, from_, to):
            fr = tk.Frame(top, bg="#1e1e1e"); fr.pack(fill=tk.X, padx=20, pady=2)
            tk.Label(fr, text=label, fg="#ccc", bg="#1e1e1e", width=12, anchor="w").pack(side=tk.LEFT)
            v = tk.IntVar(value=int(cfg[key]))
            
            def _update(val=None, k=key):
                if val is not None:
                    val_int = int(float(val))
                    v.set(val_int)
                else:
                    val_int = v.get()
                cfg[k] = val_int
                if k == "w" and var_lock.get() and orig_asp[0]:
                    new_h = int(val_int / orig_asp[0])
                    cfg["h"] = new_h; var_h.set(new_h)
                elif k == "h" and var_lock.get() and orig_asp[0]:
                    new_w = int(val_int * orig_asp[0])
                    cfg["w"] = new_w; var_w.set(new_w)
                redraw()

            def btn_adj(amt):
                new_val = v.get() + amt
                if new_val < from_: new_val = from_
                if new_val > to: new_val = to
                v.set(new_val)
                _update()

            controls_fr = tk.Frame(fr, bg="#1e1e1e")
            controls_fr.pack(side=tk.RIGHT, fill=tk.X, expand=True)

            RoundBtn(controls_fr, text="-", bg="#333", fg="#fff", bd=0, width=2, cursor="hand2", command=lambda: btn_adj(-1)).pack(side=tk.LEFT, padx=(0,5))
            sc_ui = tk.Scale(controls_fr, from_=from_, to=to, orient=tk.HORIZONTAL, bg="#1e1e1e", fg="#1db954", bd=0, highlightthickness=0, command=_update, variable=v)
            sc_ui.pack(side=tk.LEFT, fill=tk.X, expand=True)
            RoundBtn(controls_fr, text="+", bg="#333", fg="#fff", bd=0, width=2, cursor="hand2", command=lambda: btn_adj(1)).pack(side=tk.LEFT, padx=(5,0))
            
            return v

        orig_asp = [None]
        if cfg["path"] and os.path.exists(cfg["path"]):
            try: orig_asp[0] = Image.open(cfg["path"]).width / Image.open(cfg["path"]).height
            except: pass

        var_lock = tk.BooleanVar(value=cfg.get("lock_aspect", True))
        var_interactive = tk.BooleanVar(value=cfg.get("interactive", True))
        var_smooth = tk.BooleanVar(value=cfg.get("smooth", True))
        var_fix_alpha = tk.BooleanVar(value=cfg.get("fix_alpha", False))
        var_blend = tk.StringVar(value=cfg.get("blend", "black"))
        
        sw, sh = ui_root.winfo_screenwidth(), ui_root.winfo_screenheight()
        var_x = add_slider(tr("Position X"), "x", 0, sw)
        var_y = add_slider(tr("Position Y"), "y", 0, sh)
        var_w = add_slider(tr("Width"), "w", 10, sw*2)
        var_h = add_slider(tr("Height"), "h", 10, sh*2)
        var_a = add_slider("Opacity %", "alpha", 1, 100)
        
        def update_interactive():
            cfg["interactive"] = var_interactive.get()
            if sc in active_overlays:
                win = active_overlays[sc][0]
                try:
                    hwnd = ctypes.windll.user32.GetParent(win.winfo_id())
                    style = ctypes.windll.user32.GetWindowLongW(hwnd, -20)
                    if not cfg["interactive"]: ctypes.windll.user32.SetWindowLongW(hwnd, -20, style | 0x00000020)
                    else: ctypes.windll.user32.SetWindowLongW(hwnd, -20, style & ~0x00000020)
                except: pass

        def update_render_opts():
            cfg["smooth"] = var_smooth.get()
            cfg["fix_alpha"] = var_fix_alpha.get()
            redraw()

        fr_check1 = tk.Frame(top, bg="#1e1e1e"); fr_check1.pack(fill=tk.X, padx=20, pady=(5,0))
        tk.Checkbutton(fr_check1, text=tr("Aspect ratio"), variable=var_lock, bg="#1e1e1e", fg="#ccc", selectcolor="#333", activebackground="#1e1e1e", command=lambda: cfg.update({"lock_aspect": var_lock.get()})).pack(side=tk.LEFT)
        tk.Checkbutton(fr_check1, text=tr("Interactive"), variable=var_interactive, bg="#1e1e1e", fg="#ccc", selectcolor="#333", activebackground="#1e1e1e", command=update_interactive).pack(side=tk.RIGHT)

        fr_check2 = tk.Frame(top, bg="#1e1e1e"); fr_check2.pack(fill=tk.X, padx=20, pady=(0,0))
        tk.Checkbutton(fr_check2, text=tr("Smoothing"), variable=var_smooth, bg="#1e1e1e", fg="#ccc", selectcolor="#333", activebackground="#1e1e1e", command=update_render_opts).pack(side=tk.LEFT)
        tk.Checkbutton(fr_check2, text=tr("Hard edges (Alpha)"), variable=var_fix_alpha, bg="#1e1e1e", fg="#ccc", selectcolor="#333", activebackground="#1e1e1e", command=update_render_opts).pack(side=tk.RIGHT)

        fr_blend = tk.Frame(top, bg="#1e1e1e"); fr_blend.pack(fill=tk.X, padx=20, pady=(5,0))
        tk.Label(fr_blend, text=tr("Blend:"), fg="#ccc", bg="#1e1e1e").pack(side=tk.LEFT)
        
        def on_blend_change(*args):
            b_val = var_blend.get()
            b_map = {tr("Normal (Black Key)"): "black", tr("Light (White Key)"): "white", tr("Chroma key (Magenta)"): "magenta"}
            cfg["blend"] = b_map.get(b_val, "black")
            redraw()
            
        blend_opts = [tr("Normal (Black Key)"), tr("Light (White Key)"), tr("Chroma key (Magenta)")]
        current_blend_str = [k for k, v in {tr("Normal (Black Key)"): "black", tr("Light (White Key)"): "white", tr("Chroma key (Magenta)"): "magenta"}.items() if v == cfg.get("blend", "black")][0]
        var_blend.set(current_blend_str)
        
        cb_blend = ttk.Combobox(fr_blend, textvariable=var_blend, values=blend_opts, state="readonly", width=20)
        cb_blend.pack(side=tk.RIGHT)
        cb_blend.bind("<<ComboboxSelected>>", on_blend_change)

        def poll_drag():
            if not top.winfo_exists(): return
            if sc in active_overlays:
                win = active_overlays[sc][0]
                cx, cy = win.winfo_x(), win.winfo_y()
                if cfg["x"] != cx: cfg["x"] = cx; var_x.set(cx)
                if cfg["y"] != cy: cfg["y"] = cy; var_y.set(cy)
            ui_root.after(100, poll_drag)
        poll_drag()

        def close_editor():
            save_config()
            top.destroy()
        
        RoundBtn(top, text=tr("DONE"), bg="#1db954", fg="#fff", font=("Consolas", 12, "bold"), bd=0, cursor="hand2", command=close_editor).pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=20, ipady=8)

    def restart_script():
        global hook_id
        if hook_id: ctypes.windll.user32.UnhookWindowsHookEx(hook_id)
        show_osd(f"🔄 Restarting {VERSION}")
        time.sleep(0.5)
        subprocess.Popen([sys.executable] + sys.argv)
        os._exit(0)

    def manage_app(process_name, launch_cmd, run_as_user=False, action='launch'):
        if process_name == "-1" or launch_cmd == "-1": return
        name_display = process_name.split('.')[0].upper()
        icon = asset(f"{name_display.lower()}.png")
        
        if action == 'close':
            c = False
            for p in psutil.process_iter(['name']):
                if p.info['name'] and p.info['name'].lower() == process_name.lower(): 
                    p.kill(); c = True
            if c: show_osd(name_display, icon=icon, is_close=True)
        else:
            is_r = any(p.info['name'] and p.info['name'].lower() == process_name.lower() for p in psutil.process_iter(['name']))
            if not is_r:
                launch_cmd_norm = os.path.normpath(launch_cmd)
                if run_as_user: subprocess.Popen(['explorer.exe', launch_cmd_norm])
                else: os.startfile(launch_cmd_norm)
                show_osd(name_display, icon=icon)

    _cu.GetWindowThreadProcessId.argtypes = [_H, ctypes.POINTER(wintypes.DWORD)]
    _cu.GetWindowThreadProcessId.restype = wintypes.DWORD

    def _active_app():
        # pid и имя процесса окна на переднем плане + все его дочерние процессы
        try:
            pid = wintypes.DWORD(0)
            _cu.GetWindowThreadProcessId(_cu.GetForegroundWindow(), ctypes.byref(pid))
            if not pid.value: return set(), ""
            p = psutil.Process(pid.value)
            pids = {p.pid}
            for c in p.children(recursive=True): pids.add(c.pid)
            return pids, p.name()
        except Exception:
            return set(), ""

    def _get_endpoint_volume():
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume
        dev = AudioUtilities.GetSpeakers()
        ev = getattr(dev, "EndpointVolume", None)          # новые версии pycaw
        if ev is not None: return ev
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)   # старые версии
        return ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))

    # ---- microphone mute ----
    # All mic commands go through ONE worker thread, in order: a quick push-to-talk press and
    # release can never arrive swapped, and the keyboard hook never waits for audio calls.
    mic_queue = queue.Queue()
    mic_worker = {"t": None}

    def _get_mic_endpoint():
        from comtypes import CLSCTX_ALL
        from pycaw.pycaw import IAudioEndpointVolume
        dev = None
        try: dev = AudioUtilities.GetMicrophone()
        except Exception: dev = None
        if dev is None:
            dev = AudioUtilities.GetDeviceEnumerator().GetDefaultAudioEndpoint(1, 0)   # eCapture, eConsole
        ev = getattr(dev, "EndpointVolume", None)          # newer pycaw
        if ev is not None: return ev
        iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)   # older pycaw
        return ctypes.cast(iface, ctypes.POINTER(IAudioEndpointVolume))

    def _mic_loop():
        try:
            import comtypes
            comtypes.CoInitialize()
        except Exception:
            pass
        while True:
            cmd, mute, osd = mic_queue.get()
            try:
                ev = _get_mic_endpoint()        # fetched each time: the default mic may change
                cur = bool(ev.GetMute())
                new = (not cur) if cmd == "toggle" else bool(mute)
                if new != cur: ev.SetMute(1 if new else 0, None)
                if osd: show_osd("🔇 Mic muted" if new else "🎤 Mic on")
            except Exception as e:
                _runlog("MIC ERROR: " + repr(e))
                if osd: show_osd("✗ Microphone not found")

    def mic_command(cmd, mute=None, osd=True):
        if mic_worker["t"] is None or not mic_worker["t"].is_alive():
            mic_worker["t"] = threading.Thread(target=_mic_loop, daemon=True, name="mic")
            mic_worker["t"].start()
        mic_queue.put((cmd, mute, osd))

    def _mic_on_press(cfg):
        mode = cfg.get("MicMode", "toggle")
        if mode == "ptt": mic_command("set", False, osd=False)
        elif mode == "ptm": mic_command("set", True, osd=False)
        else:
            play_action_sound()
            mic_command("toggle")

    def _mic_on_release(cfg):
        mode = cfg.get("MicMode", "toggle")
        if mode == "ptt": mic_command("set", True, osd=False)
        elif mode == "ptm": mic_command("set", False, osd=False)

    def change_vol(d, target_proc="spotify.exe", mode="process", levels=None):
        delay = 120
        try:
            import comtypes
            comtypes.CoInitialize()
            aud = vol_audio_cfg
            lim = aud.get("limit", 65) / 100.0
            targets = []      # (getter, setter)
            app_name = target_proc
            if mode == "system":
                ev = _get_endpoint_volume()
                targets.append((ev.GetMasterVolumeLevelScalar, lambda x, ev=ev: ev.SetMasterVolumeLevelScalar(x, None)))
            else:
                sessions = AudioUtilities.GetAllSessions()
                if mode == "active":
                    pids, fg_name = _active_app()
                    app_name = fg_name
                    found = [s for s in sessions if getattr(s, "ProcessId", 0) in pids]
                    if not found and fg_name:
                        found = [s for s in sessions if s.Process and s.Process.name().lower() == fg_name.lower()]
                else:
                    found = [s for s in sessions if s.Process and s.Process.name().lower() == target_proc.lower()]
                for s in found:
                    v = s._ctl.QueryInterface(ISimpleAudioVolume)
                    targets.append((v.GetMasterVolume, lambda x, v=v: v.SetMasterVolume(x, None)))
            for get_v, set_v in targets:
                curr = round(get_v(), 3)
                curr_pct = curr * 100
                if curr_pct <= aud.get("low_thresh", 15):
                    step = aud.get("low_step", 1) / 100.0
                    delay = aud.get("low_delay", 150)
                elif curr_pct <= aud.get("mid_thresh", 50):
                    step = aud.get("mid_step", 5) / 100.0
                    delay = aud.get("mid_delay", 120)
                else:
                    step = aud.get("high_step", 3) / 100.0
                    delay = aud.get("high_delay", 100)
                if levels:
                    # режим точек: переходим к следующей точке по кругу (0% → 50% → 100% → 0%)
                    cur_pct = curr * 100
                    nxt = next((l for l in levels if l > cur_pct + 0.5), levels[0])
                    new_v = max(0.0, min(lim, round(nxt / 100.0, 3)))
                else:
                    new_v = max(0.0, min(lim, round(curr + (step * d), 3)))
                set_v(new_v)
                prog_disp = new_v / lim if lim > 0 else 0
                pct = f"{int(round(new_v * 100))}%"
                if mode == "system":
                    show_osd(tr("System: {}").format(pct), progress=prog_disp)
                else:
                    base = app_name.rsplit(".", 1)[0] if app_name else ""
                    msg = pct if mode == "process" else (f"{base}: {pct}" if base else pct)
                    show_osd(msg, icon=asset(f"{base.lower()}.png"), progress=prog_disp)
            comtypes.CoUninitialize()
        except Exception:
            pass
        return delay

    def volume_repeater():
        while vol_dir != 0:
            delay = change_vol(vol_dir, vol_target, vol_mode)
            time.sleep(delay / 1000.0)

    LANG_CODES = {"ENG": 0x04090409, "RUS": 0x04190419, "DE": 0x04070407,
                  "FRA": 0x040C040C, "ESP": 0x0C0A0C0A, "UKR": 0x04220422}

    def switch_layout_cycle(lang_str):
        """Switches the layout of the active window to the next language in the list, cycling."""
        names = [x.strip().upper() for x in (lang_str or "").split(",") if x.strip().upper() in LANG_CODES]
        if not names: return None
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        tid = ctypes.windll.user32.GetWindowThreadProcessId(hwnd, None)
        cur = ctypes.windll.user32.GetKeyboardLayout(tid) & 0xFFFF
        ids = [LANG_CODES[n] & 0xFFFF for n in names]
        idx = ids.index(cur) if cur in ids else -1
        nxt = names[(idx + 1) % len(names)]
        ctypes.windll.user32.PostMessageW(hwnd, 0x0050, 0, LANG_CODES[nxt])
        return nxt

    # clean2;0: эти процессы никогда не закрываются (системные, сама программа, интерпретатор)
    CLEAN_PROTECTED = {
        "explorer.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe", "searchhost.exe",
        "searchapp.exe", "runtimebroker.exe", "sihost.exe", "ctfmon.exe", "taskhostw.exe", "dwm.exe",
        "textinputhost.exe", "applicationframehost.exe", "fontdrvhost.exe", "conhost.exe", "cmd.exe",
        "powershell.exe", "pwsh.exe", "windowsterminal.exe", "securityhealthsystray.exe", "smartscreen.exe",
        "audiodg.exe", "dllhost.exe", "wmiprvse.exe", "svchost.exe", "lockapp.exe", "systemsettings.exe",
        "widgets.exe", "csrss.exe", "winlogon.exe", "services.exe", "lsass.exe", "smss.exe", "wininit.exe",
        "spoolsv.exe", "msmpeng.exe", "nissrv.exe", "system", "registry", "memory compression", "idle",
        "python.exe", "pythonw.exe", "numbinder.exe",
    }

    def _press_media_key(key):
        """Taps a media key (play/pause, next, prev, stop, mute) as a real keyboard event."""
        vk = next((m[2] for m in MEDIA_KEYS if m[0] == key), MEDIA_KEYS[0][2])
        u32 = ctypes.windll.user32
        u32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.02)
        u32.keybd_event(vk, 0, 0x0002, 0)

    def _parse_clean_keep(text):
        """'discord, telegram.exe' -> {'discord.exe', 'telegram.exe'} (lower case)."""
        out = set()
        for part in re.split(r"[,;\n]+", text or ""):
            name = part.strip().lower()
            if not name: continue
            if not name.endswith(".exe"): name += ".exe"
            out.add(name)
        return out

    def clean_processes(keep=frozenset()):
        """clean2;0: closes the current user's apps, except system, protected and user-excluded ones."""
        me = os.getpid()
        try: my_user = psutil.Process(me).username()
        except Exception: my_user = None
        closed = 0
        for p in psutil.process_iter(["pid", "name", "username"]):
            try:
                name = (p.info.get("name") or "").lower()
                if not name or p.info["pid"] in (0, 4, me) or name in CLEAN_PROTECTED or name in keep: continue
                if my_user and p.info.get("username") != my_user: continue
                p.kill()
                closed += 1
            except Exception:
                pass
        show_osd(f"clean2;0: {closed}")

    def execute_action(sc, cfg, is_second_action=False):
        t = cfg.get("Type")
        if t and t != "none": play_action_sound()
        if t == "exec":
            path, proc_name, admin = cfg.get("Path"), cfg.get("ProcessName"), cfg.get("AdminRights") == 1
            if is_second_action: manage_app(proc_name, path, action='close')
            else: manage_app(proc_name, path, run_as_user=not admin, action='launch')
        elif t == "lang" and not is_second_action:
            nxt = switch_layout_cycle(cfg.get("Language", ""))
            if nxt: show_osd(tr("🌐 Layout: {}").format(nxt))
        elif t == "clean" and is_second_action:
            threading.Thread(target=clean_processes, args=(_parse_clean_keep(cfg.get("CleanKeep", "")),), daemon=True).start()
        elif t and t.startswith("mod:") and (not is_second_action or MODULES.get(t[4:], {}).get("info", {}).get("hold")):
            mid = t[4:]
            m = MODULES.get(mid)
            if not m:
                show_osd(f"✗ module '{mid}' not found")
            else:
                ctx = ModuleContext(mid)
                ctx.is_hold = bool(is_second_action)
                def _run_module(m=m, cfg=cfg, ctx=ctx):
                    try: m["run"](ctx, cfg)
                    except Exception as e:
                        _runlog(f"MODULE RUN ERROR {ctx.module_id}:\n" + traceback.format_exc())
                        ctx.osd(f"✗ {ctx.module_id}: {e}")
                threading.Thread(target=_run_module, daemon=True).start()
        elif t == "restart" and not is_second_action: restart_script()
        elif t == "media" and not is_second_action: _press_media_key(cfg.get("MediaKey", "playpause"))
        elif t == "overlay":
            if is_second_action: ui_root.after(0, lambda: open_overlay_settings(sc))
            else: ui_root.after(0, lambda: toggle_overlay(sc))
        elif t == "crosshair":
            ui_root.after(0, lambda: crosshair_action(sc, cfg, is_second_action))
        elif t == "light macro" and not is_second_action:
            hk_keys = list(cfg.get("Hotkey", []))
            threading.Thread(target=lambda: send_hotkey(hk_keys), daemon=True).start()

    # ================= Launch\\Close app: действия по триггерам =================
    EXEC_CLICK_WINDOW = 0.5   # пауза, после которой серия нажатий считается законченной
    EXEC_HOLD_MIN = 0.3       # короче этого — это клик, а не удержание
    exec_clicks = {}

    def _get_actions(cfg):
        acts = cfg.get("Actions")
        if isinstance(acts, list): return acts
        # старые настройки: ActionTime — действие по задержке/клику, SecondActionTime — удержание
        out = []
        try: act = float(cfg.get("ActionTime", 0) or 0)
        except (TypeError, ValueError): act = 0.0
        if act > 0: out.append({"trigger": "hold", "value": act, "action": "launch"})
        else: out.append({"trigger": "count", "value": 1, "action": "launch"})
        try: sec = float(cfg.get("SecondActionTime", -1) or -1)
        except (TypeError, ValueError): sec = -1.0
        if sec > 0: out.append({"trigger": "hold", "value": sec, "action": "close"})
        return out

    def _usable_path(p):
        return bool(p) and p not in ("-1", ".") and os.path.isfile(p)

    def _resolve_exec_path(proc, path):
        """Path for launching: the saved one, or the exe of the picked app (from the app catalog)."""
        if _usable_path(path): return path
        info = app_info(proc)
        if info and _usable_path(info.get("path")): return info["path"]
        return path

    def _run_exec_action(cfg, action):
        path, proc, admin = cfg.get("Path"), cfg.get("ProcessName"), cfg.get("AdminRights") == 1
        play_action_sound()
        if action in ("launch", "restart"):
            path = _resolve_exec_path(proc, path)
            if not _usable_path(path):
                show_osd("✗ App path not set. Open the button and choose the app again.")
                return
        if action == "launch":
            manage_app(proc, path, run_as_user=not admin, action="launch")
        elif action == "close":
            manage_app(proc, path, action="close")
        elif action == "restart":
            manage_app(proc, path, action="close")
            threading.Timer(1.0, lambda: manage_app(proc, path, run_as_user=not admin, action="launch")).start()
        elif action == "tray":
            ui_root.after(0, ui_root.withdraw)

    def _exec_count_action(cfg, counts, n):
        a = next((x for x in counts if int(x["value"]) == n), None)
        if a: _run_exec_action(cfg, a["action"])

    def _exec_fire_clicks(sc):
        cs = exec_clicks.get(sc)
        if not cs: return
        n = cs["n"]; cs["n"] = 0; cs["timer"] = None
        cfg = MACRO_CONFIG.get(str(sc))
        if not cfg: return
        counts = [a for a in _get_actions(cfg) if a.get("trigger") == "count"]
        _exec_count_action(cfg, counts, n)

    def _exec_release(sc):
        st = active_keys.pop(sc, None)
        if not st or not st.get("exec"): return
        cfg = MACRO_CONFIG.get(str(sc))
        if not cfg: return
        acts = _get_actions(cfg)
        dur = time.time() - st["t0"]
        holds = [a for a in acts if a.get("trigger") == "hold"]
        if holds and dur >= EXEC_HOLD_MIN:
            best = min(holds, key=lambda a: abs(float(a["value"]) - dur))
            _run_exec_action(cfg, best["action"])
            return
        counts = [a for a in acts if a.get("trigger") == "count"]
        cs = exec_clicks.setdefault(sc, {"n": 0, "timer": None})
        cs["n"] += 1
        if cs["timer"]:
            cs["timer"].cancel(); cs["timer"] = None
        if any(int(a["value"]) >= 2 for a in counts):
            cs["timer"] = threading.Timer(EXEC_CLICK_WINDOW, _exec_fire_clicks, args=(sc,))
            cs["timer"].start()
        else:
            n = cs["n"]; cs["n"] = 0
            _exec_count_action(cfg, counts, n)

    # ================= ЯДЕРНЫЙ ХУК =================
    def handle_press(sc):
        sc_str = str(sc)
        if sc_str not in MACRO_CONFIG: return
        cfg = MACRO_CONFIG[sc_str]
        t = cfg.get("Type")
        
        if t == "volume":
            if sc not in active_keys:
                active_keys[sc] = {'triggered': True}
                play_action_sound()
                global vol_dir, vol_thread, vol_target, vol_audio_cfg, vol_mode
                vol_dir = cfg.get("VolumeDirection", 1)
                vol_target = cfg.get("ProcessName", "spotify.exe")
                vol_mode = cfg.get("VolumeTarget", "process")
                vol_audio_cfg = cfg.get("Audio", MACRO_TEMPLATE["Audio"].copy())
                if cfg.get("VolumeMode") == "steps":
                    pts = sorted({int(x) for x in cfg.get("VolumeSteps", []) if str(x).lstrip("-").isdigit()})
                    if pts:
                        # режим точек: одно нажатие — один шаг, держать не нужно
                        threading.Thread(target=change_vol, args=(0, vol_target, vol_mode, pts), daemon=True).start()
                        return
                if not vol_thread or not vol_thread.is_alive():
                    vol_thread = threading.Thread(target=volume_repeater, daemon=True); vol_thread.start()
            return

        if t == "exec":
            if sc not in active_keys:
                active_keys[sc] = {'exec': True, 't0': time.time()}
            return

        if t == "mic":
            if sc not in active_keys:          # key repeat while holding is ignored
                active_keys[sc] = {'mic': True}
                _mic_on_press(cfg)
            return

        if sc not in active_keys:
            act_time, sec_time = float(cfg.get("ActionTime", 0)), float(cfg.get("SecondActionTime", -1))
            if t == "crosshair" and (cfg.get("Crosshair") or {}).get("mode") == "smart":
                act_time = 0.0
                if sec_time <= 0: sec_time = 0.5
            t1, t2 = None, None
            if act_time > 0: t1 = threading.Timer(act_time, lambda: [active_keys[sc].update({'trig_primary': True}), execute_action(sc_str, cfg, False)])
            if sec_time > 0: t2 = threading.Timer(sec_time, lambda: [active_keys[sc].update({'trig_secondary': True}), execute_action(sc_str, cfg, True)])
            active_keys[sc] = {'timer1': t1, 'timer2': t2, 'trig_primary': False, 'trig_secondary': False, 'cfg': cfg}
            if t1: t1.start()
            if t2: t2.start()

    def handle_release(sc):
        sc_str = str(sc)
        if sc_str not in MACRO_CONFIG: return
        cfg = MACRO_CONFIG[sc_str]
        t = cfg.get("Type")
        
        if t == "volume":
            if sc in active_keys: del active_keys[sc]
            if not any(MACRO_CONFIG.get(str(k), {}).get("Type") == "volume" for k in active_keys):
                global vol_dir; vol_dir = 0
            return

        if t == "exec":
            _exec_release(sc)
            return

        if t == "mic":
            if active_keys.pop(sc, None) is not None: _mic_on_release(cfg)
            return

        if sc in active_keys:
            state = active_keys.pop(sc)
            if state['timer1']: state['timer1'].cancel()
            if state['timer2']: state['timer2'].cancel()
            if float(cfg.get("ActionTime", 0)) == 0 and not state['trig_secondary']: execute_action(sc_str, cfg, False)

    def hook_thread():
        global hook_id
        user32 = ctypes.WinDLL('user32', use_last_error=True)
        class KBDLL(ctypes.Structure):
            _fields_ = [("vk", wintypes.DWORD), ("sc", wintypes.DWORD), ("fl", wintypes.DWORD), ("tm", wintypes.DWORD), ("ex", ctypes.POINTER(wintypes.ULONG))]

        HOOKPROC = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.argtypes = (ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        user32.CallNextHookEx.restype = ctypes.c_long
        user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD)
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.UnhookWindowsHookEx.argtypes = (ctypes.c_void_p,)

        @HOOKPROC
        def hook_proc(nCode, wParam, lParam):
            try:
                if nCode >= 0:
                    kb = ctypes.cast(lParam, ctypes.POINTER(KBDLL)).contents
                    sc, fl = kb.sc, kb.fl
                    # Extended keys (flag 1) are stored as scan + 256: numpad Enter = 284, Up = 328...
                    # Only keys in allowed_keys are taken over: the numpad, plus the extended block when it is on.
                    if fl & 1: sc = sc + 256
                    if not (fl & 0x10) and macro_enabled and str(sc) in allowed_keys and str(sc) not in LOCKED_SC and str(sc) in MACRO_CONFIG and MACRO_CONFIG[str(sc)].get("Type") != "none":
                        if wParam in (0x0100, 0x0104): 
                            handle_press(sc); return 1
                        elif wParam in (0x0101, 0x0105): 
                            handle_release(sc); return 1
            except: pass
            return user32.CallNextHookEx(None, nCode, wParam, lParam)

        hook_id = user32.SetWindowsHookExW(13, hook_proc, None, 0)
        m = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(m), None, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(m))
            user32.DispatchMessageW(ctypes.byref(m))

    threading.Thread(target=hook_thread, daemon=True).start()
    
    show_osd(f"🚀 numbinder {VERSION}")
    ui_root.after(2000, _maybe_show_whats_new)
    ui_root.after(8000, _periodic_update_check)
    _runlog("mainloop start")
    _runlog(f"SOUND FILE: {_find_action_sound()}")
    ui_root.mainloop()
    _runlog("mainloop returned normally")

except BaseException as e:
    _runlog("STARTUP EXCEPTION:\n" + traceback.format_exc())
    ctypes.windll.user32.MessageBoxW(0, _crash_text("Launch error:", "Startup error:") + f"\n{e}\n\n" + _crash_text("See the crashlogs folder", "See the crashlogs folder"), "numbinder Crash", 0x10)