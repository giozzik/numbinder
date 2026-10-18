import sys
import traceback
import ctypes
import os
import datetime as _dt
import atexit
import threading as _th

# ---- Лог на каждый запуск: C:\numbinder\crashlogs\run_<дата>_pid<N>.txt ----
PATH_CRASH_DIR = r"C:\numbinder\crashlogs"
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
        with open(r"C:\numbinder\config.json", "r", encoding="utf-8") as _f:
            return json.load(_f).get("AppSettings", {}).get("lang", "ru")
    except Exception:
        return "ru"

def _crash_text(ru, en):
    return en if _crash_lang() == "en" else ru

def global_exception_handler(exc_type, exc_value, exc_traceback):
    tb_text = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    _runlog("UNHANDLED:\n" + tb_text)
    ctypes.windll.user32.MessageBoxW(0, _crash_text("Критическая ошибка запуска!", "Critical startup error!") + f"\n\n{tb_text}", "numbinder Crash", 0x10 | 0x40000)
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
    if ctypes.windll.kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
        _runlog("another numbinder instance is already running -> exit 0")
        ctypes.windll.user32.MessageBoxW(0, _crash_text("numbinder уже запущен.", "numbinder is already running."), "numbinder", 0x40)
        sys.exit(0)

    # ================= НАСТРОЙКИ =================
    VERSION = "v1.29.0"
    VOLUME_LIMIT = 0.65 
    macro_enabled = True 
    active_keys = {}
    osd_queue = queue.Queue()
    vol_dir = 0
    vol_target = ""
    vol_mode = "process"
    vol_thread = None
    secret_buffer = ""

    PATH_DIR = r"C:\numbinder"
    WIN_W, WIN_H = 444, 704   # размер окна фиксированный
    script_path = os.path.abspath(__file__)
    # Все картинки и звук лежат в C:\numbinder\assets\. Старое расположение (корень папки) тоже поддерживается.
    PATH_ASSETS = os.path.join(PATH_DIR, "assets")
    def asset(rel):
        """Все картинки и звук берутся ТОЛЬКО из C:\\numbinder\\assets\\."""
        return os.path.join(PATH_ASSETS, rel)
    _resolved_warned = set()
    def resolve_icon(p):
        """Если путь из настроек кнопки не существует, берём файл с тем же именем из assets\\."""
        if not p or p == "-1" or os.path.exists(p): return p
        cand = asset(os.path.basename(p))
        if os.path.exists(cand): return cand
        if p not in _resolved_warned:
            _resolved_warned.add(p)
            _runlog(f"ICON NOT FOUND: {p} (и нет {cand})")
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
        "82": "0", "83": "."
    }

    MACRO_TEMPLATE = {
        "Type": "none", "Language": "-1", "Path": "-1", "ProcessName": "-1", 
        "ActionTime": 0, "SecondActionTime": -1, "AdminRights": -1, "VolumeDirection": 1, "Desc": tr("Новый макрос"),
        "IconPath": "", "IconColor": "#ffffff",
        "Audio": {"limit": 65, "low_thresh": 15, "low_step": 1, "low_delay": 150, "mid_thresh": 50, "mid_step": 5, "mid_delay": 120, "high_step": 3, "high_delay": 100},
        "Overlay": {"path": "", "x": -1, "y": -1, "w": 200, "h": 200, "alpha": 80, "lock_aspect": True, "interactive": True, "smooth": True, "fix_alpha": False, "blend": "black"},
        "Crosshair": {"mode": "toggle", "name": "По умолчанию", "list": []},
        "Hotkey": []
    }

    DEFAULT_CONFIG = {
        "_version": VERSION,
        "AppSettings": {"show_labels": True, "autostart": False, "dev_unlocked": False, "dev_enabled": False, "osd_scale": 1.0, "osd_x": 50, "osd_y": 5, "action_sound": True, "action_sound_volume": 100, "osd_text_color": "#cccccc", "osd_border_color": "#c7c7c7", "osd_bg_color": "#202020", "osd_glow_color": "#ebebeb", "lang": "ru"},
        "DevSettings": {
            "scale": 1.11, "base_size": 81, "spacing": 79, 
            "color_active": "#1db954", "color_inactive": "#3a3a3a",
            "text_x": 29, "text_y": 21, "text_size": 12,
            "text_x_nlk": 29, "text_y_nlk": 21, "text_size_nlk": 12,
            "text_x_ent": 29, "text_y_ent": 21, "text_size_ent": 12,
            "hover_scale": 1.3, "hover_y": 13, "hover_overlay": 20, "color_glow": "#1db954",
            "win_w": 444, "win_h": 704, "win_pad": 12, "hover_blur": 15,
            
            "theme_grad_top": "#2a2a2a", "theme_grad_bot": "#202020",
            "corner_style": 2, "window_alpha_pct": 100
        },
        "Crosshairs": {
            "По умолчанию": {
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
        ctypes.windll.user32.MessageBoxW(0, tr("Сбой анимации или Tkinter!\n\nОшибка: {}\n\nСмотри папку C:\\numbinder\\crashlogs\\").format(val), "Tkinter Crash", 0x10 | 0x40000)
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

    _EN_MAP = {"💡 ОВЕРЛЕЙ\n\nКороткое нажатие — Вкл/Выкл\nУдержание (Hold) — Открыть студию настройки": "💡 OVERLAY\n\nShort press — On/Off\nHold — Open the overlay studio", 'Имя': 'Name', 'Нет': 'None', 'Фон': 'Background', 'Круг': 'Circle', 'Цвет': 'Color', 'Цель': 'Target', 'Выбор': 'Choose', 'Крест': 'Cross', 'Назад': 'Back', 'Текст': 'Text', 'Точка': 'Dot', 'Выход': 'Exit', 'Высота': 'Height', 'ГОТОВО': 'DONE', 'Отмена': 'Cancel', 'Патчер': 'Patcher', 'Прицел': 'Crosshair', 'Тёмный': 'Dark', 'Ширина': 'Width', 'Закрыть': 'Close', 'Обводка': 'Outline', 'Прицелы': 'Crosshairs', 'Пёстрый': 'Busy', 'Светлый': 'Light', 'Удалить': 'Delete', 'Шаг (%)': 'Step (%)', 'Вкл/Выкл': 'On/Off', 'Загрузить': 'Load', 'Картинка:': 'Image:', 'Позиция X': 'Position X', 'Позиция Y': 'Position Y', 'Пропорции': 'Aspect ratio', 'Сохранить': 'Save', 'Цвет Glow': 'Glow Color', 'Настройки': 'Settings', '3. Обводка': '3. Outline', 'Выбрать...': 'Browse...', 'Кнопка ВКЛ': 'Button ON', 'Наложение:': 'Blend:', 'Не выбрано': 'Not selected', 'ПРЕВЬЮ 65%': 'PREVIEW 65%', 'Т-образный': 'T-shape', 'Тихая зона': 'Quiet zone', 'Цвет шапки': 'Header color', 'Вся система': 'Whole system', 'Кнопка ВЫКЛ': 'Button OFF', 'Код прицела': 'Crosshair code', 'Оверлей ВКЛ': 'Overlay ON', 'Прицел ВЫКЛ': 'Crosshair OFF', 'Сглаживание': 'Smoothing', 'ТЕКСТ ENTER': 'ENTER TEXT', 'ТЕКСТ ОБЩИЙ': 'GENERAL TEXT', 'Тип прицела': 'Crosshair type', 'Громкая зона': 'Loud zone', 'Новый макрос': 'New macro', 'Порог до (%)': 'Threshold up to (%)', 'Средняя зона': 'Medium zone', 'Цвет обводки': 'Outline color', 'Цвет прицела': 'Crosshair color', 'Выбор клавиши': 'Choose key', 'Задержка (мс)': 'Delay (ms)', 'Интерактивное': 'Interactive', 'Ошибка записи': 'Write error', 'Позиция X (%)': 'Position X (%)', 'Позиция Y (%)': 'Position Y (%)', 'Применить код': 'Apply code', 'Режим прицела': 'Crosshair mode', 'СОХРАНИТЬ ВСЁ': 'SAVE ALL', 'ТЕКСТ NUMLOCK': 'NUMLOCK TEXT', 'Путь до иконки': 'Icon path', 'Путь до файла.': 'File path.', 'Размер (Scale)': 'Size (Scale)', 'СТУДИЯ ОВЕРЛЕЯ': 'OVERLAY STUDIO', 'Сбросить цвета': 'Reset colors', 'Студия Оверлея': 'Overlay Studio', 'Точка в центре': 'Center dot', 'ГЕОМЕТРИЯ СЕТКИ': 'GRID GEOMETRY', 'Громкость звука': 'Sound volume', 'Названия кнопок': 'Button labels', 'Размытие (Blur)': 'Blur', 'Свечение текста': 'Text glow', 'Скопировать код': 'Copy code', 'Включить обводку': 'Enable outline', 'Длина линий (px)': 'Line length (px)', 'Прицел не найден': 'Crosshair not found', 'Прозрачность (%)': 'Opacity (%)', 'Цвет поверхности': 'Surface color', 'Комбинация клавиш': 'Key combination', 'Лимит громкости %': 'Volume limit %', 'Размер точки (px)': 'Dot size (px)', 'Уведомления (OSD)': 'Notifications (OSD)', 'Угол поворота (°)': 'Rotation angle (°)', 'Цвета уведомлений': 'Notification colors', 'ЭФФЕКТЫ НАВЕДЕНИЯ': 'HOVER EFFECTS', 'Попытка запуска...': 'Launching...', 'Толщина линий (px)': 'Line thickness (px)', 'Хромакей (Magenta)': 'Chroma key (Magenta)', 'Язык переключения.': 'Language to switch to.', 'Активное приложение': 'Active application', 'Выбрать сохранённый': 'Choose saved', 'Зазор / отступ (px)': 'Gap / offset (px)', 'Конструктор прицела': 'Crosshair designer', 'Обычное (Black Key)': 'Normal (Black Key)', 'Прицел: список пуст': 'Crosshair: list is empty', 'Резкие края (Alpha)': 'Hard edges (Alpha)', 'Светлое (White Key)': 'Light (White Key)', 'Сохранённые прицелы': 'Saved crosshairs', '1. Форма и геометрия': '1. Shape and geometry', 'Введите имя прицела.': 'Enter a crosshair name.', 'Глобальные настройки': 'Global settings', 'Прозрачность окна, %': 'Window opacity, %', 'Толщина обводки (px)': 'Outline thickness (px)', 'Оверлей: Нет картинки': 'Overlay: No image', '2. Цвет и прозрачность': '2. Color and opacity', 'Процесс (поле Process)': 'Process (Process field)', 'Долгое удержание (сек).': 'Long hold (sec).', 'Запуск вместе с Windows': 'Start with Windows', 'Запуск от имени Админа.': 'Run as Administrator.', 'Такой прицел не найден.': 'That crosshair was not found.', 'Выберите язык из списка.': 'Choose a language from the list.', 'Какой прицел показывать.': 'Which crosshair to show.', 'Настройки звука процесса': 'Process sound settings', 'Применить патч из буфера': 'Apply patch from clipboard', 'Прозрачность обводки (%)': 'Outline opacity (%)', 'DEV режим (горячие патчи)': 'DEV mode (hot patches)', 'Выбор основного действия.': 'Choose the main action.', 'Умный (удержание + смена)': 'Smart (hold + cycle)', 'Имя процесса в диспетчере.': 'Process name in Task Manager.', 'Чьей громкостью управлять.': 'Whose volume to control.', 'Не удалось скопировать код.': 'Could not copy the code.', 'Звук при срабатывании кнопки': 'Sound on button press', 'Открыть конструктор прицелов': 'Open crosshair designer', 'Авто-настройка второй кнопки.': 'Auto-configure the second button.', 'Патчер: синтаксическая ошибка': 'Patcher: syntax error', 'Как кнопка управляет прицелом.': 'How the button controls the crosshair.', 'Код скопирован в буфер обмена.': 'Code copied to clipboard.', 'Направление регулировки звука.': 'Volume adjustment direction.', 'ОФОРМЛЕНИЕ (Windows 11 native)': 'APPEARANCE (Windows 11 native)', 'Сбросить к значениям по умолчанию': 'Reset to default values', 'Скругление 0=нет 1=малое 2=большое': 'Corner rounding 0=none 1=small 2=large', 'Задержка перед срабатыванием (сек).': 'Delay before triggering (sec).', 'Прицел по умолчанию удалить нельзя.': 'The default crosshair cannot be deleted.', 'Укажите путь до картинки (png/jpg).': 'Specify the path to an image (png/jpg).', 'Определяет, что будет делать кнопка.': 'Determines what the button will do.', 'Неверный или повреждённый код прицела.': 'Invalid or corrupted crosshair code.', 'Библиотеки загружены! Зачистка призраков...': 'Libraries loaded! Cleaning up ghosts...', 'Укажите абсолютный путь до файла программы.': 'Specify the absolute path to the program file.', 'Точное имя процесса (например, spotify.exe).': 'Exact process name (e.g. spotify.exe).', 'Нажмите на клавишу, чтобы добавить её в комбинацию': 'Click a key to add it to the combination', 'Прицелы в ротации (порядок — по очерёдности выбора)': 'Crosshairs in rotation (order = selection order)', 'Укажите 0 для моментального срабатывания при клике.': 'Set 0 to trigger instantly on click.', 'Up: Увеличивает громкость.\nDown: Уменьшает громкость.': 'Up: increases volume.\nDown: decreases volume.', '💡 ПРИЦЕЛ\n\nНажатие — показать/скрыть выбранный прицел': '💡 CROSSHAIR\n\nPress — show/hide the selected crosshair', 'Ошибка: В буфере не найден ни патч, ни полный код скрипта.': 'Error: no patch or full script code found in the clipboard.', '✅ Код полностью перезаписан! Программа будет перезапущена.': '✅ Code fully rewritten! The program will restart.', 'Программа будет запущена с максимальными правами в Windows.': 'The program will be launched with maximum rights in Windows.', '🔓 Инициализация разработчика...\n\nDEV Режим разблокирован!': '🔓 Developer initialization...\n\nDEV Mode unlocked!', '✅ Микро-патч успешно применен! Программа будет перезапущена.': '✅ Micro-patch applied successfully! The program will restart.', 'Позволяет сразу назначить обратное действие на другую кнопку.': 'Lets you immediately assign the reverse action to another button.', 'Время удержания для второго действия. Укажите 1.0 для оверлея.': 'Hold time for the second action. Set 1.0 for overlay.', 'Прицелы создаются в конструкторе: Настройки → Открыть конструктор прицелов.': 'Crosshairs are created in the designer: Settings → Open crosshair designer.', '💡 ПРИЦЕЛ\n\nУдержание — показать/скрыть\nНажатие — следующий прицел из списка': '💡 CROSSHAIR\n\nHold — show/hide\nPress — next crosshair from the list', 'Нажмите «＋» и выберите клавишу на экранной клавиатуре. Клавиши нажимаются по порядку и отпускаются в обратном.': 'Press “+” and pick a key on the on-screen keyboard. Keys are pressed in order and released in reverse.', 'Вкл/Выкл — нажатие показывает или скрывает выбранный прицел.\n\nУмный — удержание показывает/скрывает прицел, короткое нажатие переключает на следующий из списка.': 'On/Off — pressing shows or hides the selected crosshair.\n\nSmart — holding shows/hides the crosshair, a short press switches to the next one in the list.', 'Процесс — приложение из поля Process (например, Spotify).\n\nАктивное приложение — то, окно которого сейчас на переднем плане (звук берётся и у его дочерних процессов, например у браузера).\n\nВся система — общая громкость Windows. Лимит из настроек ниже действует и здесь: поставьте 100, чтобы он не мешал.': "Process — the app from the Process field (e.g. Spotify).\n\nActive application — the window currently in the foreground (its child processes are included too, e.g. for browsers).\n\nWhole system — overall Windows volume. The limit from the settings below still applies here: set it to 100 if you don't want it in the way."}
    def tr(s):
        if MACRO_CONFIG.get("AppSettings", {}).get("lang", "ru") == "en":
            return _EN_MAP.get(s, s)
        return s
        
    for k, v in list(MACRO_CONFIG.items()):
        if k.isdigit() and isinstance(v, dict):
            if "Overlay" not in v:
                v["Overlay"] = MACRO_TEMPLATE["Overlay"].copy()
            if "Crosshair" not in v:
                v["Crosshair"] = {"mode": "toggle", "name": "По умолчанию", "list": []}
            if "Hotkey" not in v:
                v["Hotkey"] = []

    if MACRO_CONFIG.get("_version") != VERSION:
        MACRO_CONFIG["_version"] = VERSION
        with open(PATH_CONFIG, "w", encoding="utf-8") as f: json.dump(MACRO_CONFIG, f, indent=4, ensure_ascii=False)

    # ================= МОДУЛИ =================
    MODULES_DIR = os.path.join(PATH_DIR, "modules")
    MODULES = {}  # id -> {"info": dict, "run": callable, "file": str}

    def _L(ru, en):
        return en if MACRO_CONFIG["AppSettings"].get("lang", "ru") == "en" else ru

    def _mod_name(info):
        n = info.get("name", info.get("id", "?"))
        if isinstance(n, dict):
            return n.get(MACRO_CONFIG["AppSettings"].get("lang", "ru"), n.get("ru", info.get("id", "?")))
        return str(n)

    def type_to_label(t):
        if isinstance(t, str) and t.startswith("mod:"):
            m = MODULES.get(t[4:])
            return ("🧩 " + _mod_name(m["info"])) if m else t
        return t

    def label_to_type(l):
        if isinstance(l, str) and l.startswith("🧩 "):
            for mid, m in MODULES.items():
                if "🧩 " + _mod_name(m["info"]) == l: return "mod:" + mid
        return l

    def type_options():
        base = ["none", "exec", "lang", "volume", "restart", "dev patch", "overlay", "crosshair", "light macro"]
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
                    raise ValueError("в модуле нет MODULE['id'] или функции run(ctx, cfg)")
                MODULES[str(info["id"])] = {"info": info, "run": mod.run, "file": fn}
            except Exception:
                _runlog(f"MODULE LOAD FAILED {fn}:\n" + traceback.format_exc())
        # старая кнопка «Layout Fixer» -> модуль layout_fixer
        for k, v in MACRO_CONFIG.items():
            if k.isdigit() and isinstance(v, dict) and v.get("Type") == "Layout Fixer":
                v["Type"] = "mod:layout_fixer"
        _runlog("modules loaded: " + ", ".join(MODULES.keys()))

    class ModuleContext:
        """Что видит модуль: помощники без доступа к внутренностям numbinder."""
        def __init__(self, mod_id):
            self.module_id = mod_id
        def osd(self, text):
            show_osd(str(text))
        def log(self, text):
            _runlog(f"[module {self.module_id}] {text}")
        def settings(self):
            return MACRO_CONFIG.setdefault("Modules", {}).setdefault(self.module_id, {})
        def save_settings(self):
            save_config()

    _load_modules()

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
        """Скругление углов окна: радиус берётся из DevSettings['corner_radius'] (по умолчанию 32 px)."""
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

    def toggle_task_scheduler(enable):
        task_name = "numbinderAutoStart"
        exe_path = sys.executable.replace("python.exe", "pythonw.exe")
        working_dir = os.path.dirname(script_path)
        try:
            if enable:
                cmd = f'schtasks /create /tn "{task_name}" /tr "\\"{exe_path}\\" \\"{script_path}\\"" /sc onlogon /f'
                subprocess.run(cmd, shell=True, creationflags=0x08000000, cwd=working_dir)
            else:
                cmd = f'schtasks /delete /tn "{task_name}" /f'
                subprocess.run(cmd, shell=True, creationflags=0x08000000)
        except Exception as e: pass

    class RoundBtn(tk.Canvas):
        """Скруглённая кнопка на Canvas. Заменяет tk.Button, принимает те же основные параметры."""
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
    def start_move(e): ui_root.x, ui_root.y = e.x, e.y
    def stop_move(e): ui_root.x = ui_root.y = None
    def do_move(e):
        x = ui_root.winfo_x() + e.x - getattr(ui_root, 'x', 0)
        y = ui_root.winfo_y() + e.y - getattr(ui_root, 'y', 0)
        ui_root.geometry(f"+{x}+{y}")

    main_frame = tk.Frame(ui_root)
    main_frame.pack(fill=tk.BOTH, expand=True)
    canvas_numpad = tk.Canvas(main_frame, highlightthickness=0)
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
    def backup_script():
        try:
            backup_dir = os.path.join(PATH_DIR, "backups")
            os.makedirs(backup_dir, exist_ok=True)
            ts = time.strftime("%Y%m%d_%H%M%S")
            with open(script_path, 'r', encoding='utf-8') as f: cur = f.read()
            with open(os.path.join(backup_dir, f"numbinder_{ts}.pyw"), 'w', encoding='utf-8') as f: f.write(cur)
        except Exception: pass

    def check_syntax(code_str):
        try:
            compile(code_str, script_path, 'exec')
            return None
        except SyntaxError as e:
            return tr("Строка {}: {}\n\n{}").format(e.lineno, e.msg, (e.text or '').strip())

    def apply_patch_from_clipboard():
        cb = pyperclip.paste().replace('\r\n', '\n')
        if 'import sys' in cb and 'import tkinter' in cb and 'def global_exception_handler' in cb and '===PATCH_' + 'START===' not in cb:
            err = check_syntax(cb)
            if err:
                messagebox.showerror(tr("Патчер: синтаксическая ошибка"), tr("Патч НЕ применён, файл не тронут.\n\n{}").format(err))
                return
            try:
                backup_script()
                with open(script_path, 'w', encoding='utf-8') as f: f.write(cb)
                messagebox.showinfo(tr("Патчер"), tr("✅ Код полностью перезаписан! Программа будет перезапущена."))
                restart_script()
            except Exception as e: messagebox.showerror(tr("Ошибка записи"), tr("Не удалось полностью перезаписать файл:\n{}").format(e))
            return

        pattern = r'===PATCH_' + r'START===\n---FIND---\n(.*?)\n\+\+\+REPLACE\+\+\+\n(.*?)\n===PATCH_' + r'END==='
        patches = re.findall(pattern, cb, re.DOTALL)
        if not patches:
            messagebox.showerror(tr("Патчер"), tr("Ошибка: В буфере не найден ни патч, ни полный код скрипта."))
            return

        try:
            with open(script_path, 'r', encoding='utf-8') as f: source = f.read().replace('\r\n', '\n')
            for find_str, rep_str in patches:
                if find_str not in source:
                    messagebox.showerror(tr("Патчер"), tr("Сбой патча! Не удалось найти блок кода:\n\n{}...").format(find_str[:100]))
                    return
                source = source.replace(find_str, rep_str)

            err = check_syntax(source)
            if err:
                messagebox.showerror(tr("Патчер: синтаксическая ошибка"), tr("Патч НЕ применён, файл не тронут.\n\n{}").format(err))
                return

            backup_script()
            with open(script_path, 'w', encoding='utf-8') as f: f.write(source)
            messagebox.showinfo(tr("Патчер"), tr("✅ Микро-патч успешно применен! Программа будет перезапущена."))
            restart_script()
        except Exception as e: messagebox.showerror(tr("Ошибка записи"), tr("Не удалось обновить файл:\n{}").format(e))

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
            c = cc.askcolor(title=tr("Цвет"), color=MACRO_CONFIG.get("DevSettings", {}).get(key, "#ffffff"))[1]
            if c: MACRO_CONFIG["DevSettings"][key] = c; draw_numpad()
            
        def create_color_btn(parent, label, key):
            RoundBtn(parent, text=label, bg="#333", fg="#fff", bd=0, cursor="hand2", command=lambda: set_color(key)).pack(fill=tk.X, pady=2)
        
        b_theme = Collapsible(tr("ОФОРМЛЕНИЕ (Windows 11 native)"))
        create_color_btn(b_theme.content, tr("Цвет шапки"), "theme_grad_top")
        create_color_btn(b_theme.content, tr("Цвет поверхности"), "theme_grad_bot")

        b_win = Collapsible(tr("ГЕОМЕТРИЯ СЕТКИ"))
        create_slider(b_win.content, "Scale", "scale", 0.5, 2.0, 0.01, 1.11, True)
        create_slider(b_win.content, "Base", "base_size", 40, 100, 1, 81)
        create_slider(b_win.content, "Spacing", "spacing", 50, 120, 1, 79)
        create_color_btn(b_win.content, tr("Кнопка ВКЛ"), "color_active")
        create_color_btn(b_win.content, tr("Кнопка ВЫКЛ"), "color_inactive")

        b_txt = Collapsible(tr("ТЕКСТ ОБЩИЙ"))
        create_slider(b_txt.content, "X", "text_x", 0, 60, 1, 29)
        create_slider(b_txt.content, "Y", "text_y", 0, 60, 1, 21)
        create_slider(b_txt.content, "Size", "text_size", 5, 25, 1, 12)

        b_nlk = Collapsible(tr("ТЕКСТ NUMLOCK"))
        create_slider(b_nlk.content, "X", "text_x_nlk", 0, 80, 1, 29)
        create_slider(b_nlk.content, "Y", "text_y_nlk", 0, 80, 1, 21)
        create_slider(b_nlk.content, "Size", "text_size_nlk", 5, 25, 1, 12)

        b_ent = Collapsible(tr("ТЕКСТ ENTER"))
        create_slider(b_ent.content, "X", "text_x_ent", 0, 80, 1, 29)
        create_slider(b_ent.content, "Y", "text_y_ent", 0, 80, 1, 21)
        create_slider(b_ent.content, "Size", "text_size_ent", 5, 25, 1, 12)

        b_hov = Collapsible(tr("ЭФФЕКТЫ НАВЕДЕНИЯ"))
        create_slider(b_hov.content, "Scale", "hover_scale", 1.0, 2.0, 0.01, 1.3, True)
        create_slider(b_hov.content, "Y Float", "hover_y", 0, 50, 1, 13)
        create_slider(b_hov.content, tr("Размытие (Blur)"), "hover_blur", 0, 50, 1, 15)
        create_slider(b_hov.content, "Overlay %", "hover_overlay", 0, 100, 1, 20)
        create_color_btn(b_hov.content, tr("Цвет Glow"), "color_glow")

        bottom_fr = tk.Frame(box, bg="#1e1e1e")
        bottom_fr.pack(fill=tk.X, side=tk.BOTTOM)
        RoundBtn(bottom_fr, text=tr("СОХРАНИТЬ ВСЁ"), bg="#cc2929", fg="#fff", font=("Consolas", 11, "bold"), bd=0, cursor="hand2", command=lambda: [save_config(), box.destroy()]).pack(fill=tk.X, padx=20, pady=15, ipady=8)

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
        w.title(_L("numbinder — модули: важное предупреждение", "numbinder — modules: important warning"))
        w.configure(bg="#111111")
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        ww, wh = min(900, sw - 80), min(640, sh - 120)
        w.geometry(f"{ww}x{wh}+{(sw - ww) // 2}+{(sh - wh) // 2}")
        w.transient(ui_root)
        w.grab_set()
        tk.Label(w, text="⚠  " + _L("ВНИМАНИЕ: модули — это код, который запускается на вашем компьютере",
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
        RoundBtn(btns, text=_L("Отмена", "Cancel"), command=_cancel, bg="#2a2a2a", fg="#e8e8e8", activebackground="#3a3a3a",
                  activeforeground="#ffffff", relief=tk.FLAT, font=("Segoe UI", 11), padx=22, pady=8).pack(side=tk.RIGHT, padx=(12, 0))
        RoundBtn(btns, text=_L("Я понимаю риски, продолжить", "I understand the risks, continue"), command=_accept, bg="#8a2b22", fg="#ffffff",
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
                messagebox.showerror("numbinder", _L("Не удалось скопировать модуль:\n", "Could not copy the module:\n") + str(e))
                return
            _load_modules()
            _refresh_type_dropdowns()
            messagebox.showinfo("numbinder", _L("Модуль установлен. Он появится в списке «Тип» кнопок.",
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
        tk.Label(row, text=_L("Модули", "Modules"), fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        RoundBtn(row, text=_L("Открыть папку", "Open folder"), command=open_modules_folder, bg="#2a2a2a", fg="#e8e8e8",
                  activebackground="#3a3a3a", activeforeground="#ffffff", relief=tk.FLAT, font=("Segoe UI", 10), padx=12, pady=4).pack(side=tk.RIGHT, padx=(8, 0))
        RoundBtn(row, text=_L("Установить модуль…", "Install module…"), command=install_module_dialog, bg="#2a2a2a", fg="#e8e8e8",
                  activebackground="#3a3a3a", activeforeground="#ffffff", relief=tk.FLAT, font=("Segoe UI", 10), padx=12, pady=4).pack(side=tk.RIGHT)

    def build_settings_screen():
        ui_root.osd_preview_mode = True
        ui_root.after(100, lambda: globals().get('force_osd_preview', lambda: None)())
        for widget in settings_content.winfo_children(): widget.destroy()
        
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        settings_canvas.config(bg=_bg)
        settings_content.config(bg=_bg)
        
        tk.Label(settings_content, text=tr("Глобальные настройки"), fg="#ffffff", bg=_bg, font=("Segoe UI", 16, "bold")).pack(pady=(20, 10), anchor="w", padx=40)
        
        # ---- Язык интерфейса (применяется после перезапуска) ----
        lang_var = tk.StringVar(value="English" if MACRO_CONFIG["AppSettings"].get("lang", "ru") == "en" else "Русский")
        def on_lang_change(e=None):
            MACRO_CONFIG["AppSettings"]["lang"] = "en" if lang_var.get() == "English" else "ru"
            save_config()
            messagebox.showinfo("numbinder", "Restart numbinder to apply the language.\nПерезапустите numbinder, чтобы применить язык.")
        create_dropdown_row(settings_content, "Language / Язык", lang_var, ["Русский", "English"], command=on_lang_change)
        create_modules_section(settings_content)

        autostart_var = tk.BooleanVar(value=MACRO_CONFIG["AppSettings"].get("autostart", False))
        def on_autostart_toggle():
            MACRO_CONFIG["AppSettings"]["autostart"] = autostart_var.get()
            save_config()
            toggle_task_scheduler(autostart_var.get())

        auto_row = tk.Frame(settings_content, bg=_bg)
        auto_row.pack(fill=tk.X, padx=40, pady=8)
        tk.Label(auto_row, text=tr("Запуск вместе с Windows"), bg=_bg, fg="#e8e8e8", font=("Segoe UI", 11)).pack(side=tk.LEFT)
        AnimatedSwitch(auto_row, autostart_var, bg=_bg, command=on_autostart_toggle).pack(side=tk.RIGHT)

        snd_var = tk.BooleanVar(value=MACRO_CONFIG["AppSettings"].get("action_sound", True))
        def on_snd_toggle():
            MACRO_CONFIG["AppSettings"]["action_sound"] = snd_var.get()
            save_config()
        snd_row = tk.Frame(settings_content, bg=_bg)
        snd_row.pack(fill=tk.X, padx=40, pady=8)
        tk.Label(snd_row, text=tr("Звук при срабатывании кнопки"), bg=_bg, fg="#e8e8e8", font=("Segoe UI", 11)).pack(side=tk.LEFT)
        AnimatedSwitch(snd_row, snd_var, bg=_bg, command=on_snd_toggle).pack(side=tk.RIGHT)

        vol_row = tk.Frame(settings_content, bg=_bg)
        vol_row.pack(fill=tk.X, padx=40, pady=5)
        tk.Label(vol_row, text=tr("Громкость звука"), bg=_bg, fg="#e8e8e8", font=("Segoe UI", 10)).pack(side=tk.LEFT)
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

        tk.Label(settings_content, text=tr("Уведомления (OSD)"), fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
        
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

        create_osd_slider(tr("Размер (Scale)"), "osd_scale", 0.5, 3.0, 0.1, True)
        create_osd_slider(tr("Позиция X (%)"), "osd_x", 0, 100, 1)
        create_osd_slider(tr("Позиция Y (%)"), "osd_y", 0, 100, 1)

        tk.Label(settings_content, text=tr("Цвета уведомлений"), fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
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
        add_osd_color(tr("Текст"), "osd_text_color", "#cccccc")
        add_osd_color(tr("Свечение текста"), "osd_glow_color", "#ebebeb")
        add_osd_color(tr("Фон"), "osd_bg_color", "#202020")
        add_osd_color(tr("Обводка"), "osd_border_color", "#c7c7c7")
        def reset_osd_colors():
            for v, d in osd_color_vars: v.set(d)
        RoundBtn(settings_content, text=tr("Сбросить цвета"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=reset_osd_colors).pack(fill=tk.X, padx=40, pady=(5, 5), ipady=5)

        tk.Label(settings_content, text=_L("Цвета кнопок", "Button colors"), fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
        def add_btn_color(label, key, default):
            var = tk.StringVar(value=MACRO_CONFIG["DevSettings"].get(key, default))
            create_color_row(settings_content, label, var)
            def on_btn_color(*_):
                MACRO_CONFIG["DevSettings"][key] = var.get()
                save_config()
                try: draw_numpad()
                except Exception: pass
            var.trace_add("write", on_btn_color)
        add_btn_color(tr("Кнопка ВКЛ"), "color_active", "#1db954")
        add_btn_color(tr("Кнопка ВЫКЛ"), "color_inactive", "#3a3a3a")

        tk.Label(settings_content, text=tr("Прицелы"), fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(pady=(20, 5), anchor="w", padx=40)
        RoundBtn(settings_content, text=tr("Открыть конструктор прицелов"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=lambda: open_crosshair_designer()).pack(fill=tk.X, padx=40, pady=5, ipady=6)

        if MACRO_CONFIG["AppSettings"].get("dev_unlocked", False):
            dev_var = tk.BooleanVar(value=MACRO_CONFIG["AppSettings"].get("dev_enabled", False))
            def on_dev_toggle():
                MACRO_CONFIG["AppSettings"]["dev_enabled"] = dev_var.get()
                save_config()
                build_settings_screen() 
            
            dev_row = tk.Frame(settings_content, bg=_bg)
            dev_row.pack(fill=tk.X, padx=40, pady=(20, 5))
            tk.Label(dev_row, text=tr("DEV режим (горячие патчи)"), bg=_bg, fg="#f5d142", font=("Segoe UI", 11, "bold")).pack(side=tk.LEFT)
            AnimatedSwitch(dev_row, dev_var, bg=_bg, command=on_dev_toggle).pack(side=tk.RIGHT)

            if dev_var.get():
                patch_btn = RoundBtn(settings_content, text=tr("Применить патч из буфера"), bg="#c42b1c", fg="#ffffff", font=("Segoe UI", 10, "bold"), borderwidth=0, cursor="hand2", command=apply_patch_from_clipboard)
                patch_btn.pack(pady=10, ipadx=10, ipady=6)

        btn_frame_set = tk.Frame(settings_content, bg=_bg)
        btn_frame_set.pack(side=tk.BOTTOM, pady=20, fill=tk.X, padx=40)
        RoundBtn(btn_frame_set, text=tr("Назад"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11), borderwidth=0, cursor="hand2", command=lambda: show_main_screen()).pack(fill=tk.X, expand=True, ipady=6)

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

    btn_img_cache = {}
    hover_cache = {}
    btn_geom_cache = {}
    hover_state = {"sc": None, "target": None, "prog": 0.0, "job": None}

    def render_hover_frame():
        canvas_numpad.delete("hover_fx")
        canvas_numpad.delete("hover_fx_bg")
        sc = hover_state["sc"]
        target = hover_state["target"]
        
        if target is not None:
            if sc != target and hover_state["prog"] > 0: hover_state["prog"] -= 0.2
            else: hover_state["sc"] = target; hover_state["prog"] += 0.2
        else: hover_state["prog"] -= 0.2
            
        hover_state["prog"] = round(max(0.0, min(1.0, hover_state["prog"])), 1)
        p = hover_state["prog"]
        
        if p > 0 and hover_state["sc"] in btn_geom_cache:
            dev = MACRO_CONFIG.get("DevSettings", {})
            geom = btn_geom_cache[hover_state["sc"]]
            win_w = WIN_W
            win_h = WIN_H
            
            ov_alpha = int(255 * (dev.get("hover_overlay", 20) / 100.0) * p)
            if ov_alpha > 0:
                ov_key = f"ov_{ov_alpha}"
                if ov_key not in hover_cache:
                    img = Image.new("RGBA", (2000, 2000), (0, 0, 0, ov_alpha))
                    hover_cache[ov_key] = ImageTk.PhotoImage(img)
                canvas_numpad.create_image(win_w/2, win_h/2, image=hover_cache[ov_key], tags="hover_fx_bg", state="disabled")
            
            sc_scale = 1.0 + (dev.get("hover_scale", 1.3) - 1.0) * p
            draw_w, draw_h = int(geom["w"] * sc_scale), int(geom["h"] * sc_scale)
            new_cy = geom["cy"] - (dev.get("hover_y", 13) * p)
            
            gl_c = dev.get("color_glow", "#1db954")
            b_rad = int(dev.get("hover_blur", 15))
            pad = b_rad * 3 + 10 
            gl_base_key = f"gl_base_shape_{geom['cs']}_{geom['rs']}_{draw_w}_{draw_h}_{gl_c}_{b_rad}"
            gl_key = f"gl_shape_{geom['cs']}_{geom['rs']}_{draw_w}_{draw_h}_{gl_c}_{b_rad}_{p}"
            
            if gl_key not in hover_cache:
                if gl_base_key not in hover_cache:
                    w_pad, h_pad = int(draw_w + pad*2), int(draw_h + pad*2)
                    gl_img = Image.new("RGBA", (w_pad, h_pad), (0,0,0,0))
                    
                    img_t = PATH_BTN_HOR if geom["cs"] == 2 else (PATH_BTN_VERT if geom["rs"] == 2 else PATH_BTN_SINGLE)
                    try:
                        shape_img = Image.open(img_t).convert("RGBA").resize((int(draw_w), int(draw_h)), Image.Resampling.LANCZOS)
                        tr, tg, tb = int(gl_c[1:3], 16), int(gl_c[3:5], 16), int(gl_c[5:7], 16)
                        sr, sg, sb, sa = shape_img.split()
                        sr = sr.point(lambda i: i * tr / 255); sg = sg.point(lambda i: i * tg / 255); sb = sb.point(lambda i: i * tb / 255)
                        colored_shape = Image.merge('RGBA', (sr, sg, sb, sa))
                        gl_img.paste(colored_shape, (int(pad), int(pad)), colored_shape)
                    except: pass
                    
                    hover_cache[gl_base_key] = gl_img.filter(ImageFilter.GaussianBlur(b_rad))
                
                base_blur = hover_cache[gl_base_key].copy()
                alpha = base_blur.split()[3].point(lambda i: int(i * p))
                base_blur.putalpha(alpha)
                hover_cache[gl_key] = ImageTk.PhotoImage(base_blur)
            canvas_numpad.create_image(geom["cx"], new_cy, image=hover_cache[gl_key], tags="hover_fx_bg", state="disabled")
            
            img_t = PATH_BTN_HOR if geom["cs"] == 2 else (PATH_BTN_VERT if geom["rs"] == 2 else PATH_BTN_SINGLE)
            btn_key = f"hbtn_{hover_state['sc']}_{geom['color']}_{draw_w}_{draw_h}"
            if btn_key not in hover_cache:
                tinted = tint_image(img_t, geom['color'], draw_w, draw_h)
                hover_cache[btn_key] = tinted if tinted else "fail"
            
            if hover_cache[btn_key] != "fail": canvas_numpad.create_image(geom["cx"], new_cy, image=hover_cache[btn_key], tags="hover_fx", state="disabled")
            else: canvas_numpad.create_polygon([geom["cx"]-draw_w/2, new_cy-draw_h/2, geom["cx"]+draw_w/2, new_cy+draw_h/2], fill=geom['color'], tags="hover_fx", state="disabled")
            
            drawn_icon = False
            if geom['is_act'] and MACRO_CONFIG[hover_state['sc']].get("IconPath"):
                ipath = resolve_icon(MACRO_CONFIG[hover_state['sc']]["IconPath"])
                icolor = MACRO_CONFIG[hover_state['sc']].get("IconColor", "#ffffff")
                if os.path.exists(ipath):
                    ic_sz = int(min(draw_w, draw_h) * 0.45)
                    ik_key = f"icn_{hover_state['sc']}_{icolor}_{ic_sz}"
                    if ik_key not in btn_img_cache:
                        tinted_icn = tint_image(ipath, icolor, ic_sz, ic_sz)
                        if tinted_icn: btn_img_cache[ik_key] = tinted_icn
                    if ik_key in btn_img_cache:
                        canvas_numpad.create_image(geom["cx"], new_cy, image=btn_img_cache[ik_key], tags="hover_fx", state="disabled")
                        drawn_icon = True

            if MACRO_CONFIG["AppSettings"].get("show_labels", True) and not drawn_icon:
                lbl = SC_NAMES.get(hover_state['sc'], hover_state['sc'])
                t_c = "#ffffff" if geom['is_act'] else "#888888"
                cur_tx, cur_ty = (geom["cx"] - draw_w/2) + geom["t_x"]*sc_scale, (new_cy - draw_h/2) + geom["t_y"]*sc_scale
                canvas_numpad.create_text(cur_tx, cur_ty, text=lbl, fill=t_c, font=("Segoe UI", int(geom["t_size"]*sc_scale), "bold"), anchor="nw", tags="hover_fx", state="disabled")
        
        if (target is not None and p < 1.0) or (target is None and p > 0.0): hover_state["job"] = ui_root.after(15, render_hover_frame)

    def trigger_hover(sc, is_enter):
        if hover_state["job"]: ui_root.after_cancel(hover_state["job"]); hover_state["job"] = None
        hover_state["target"] = sc if is_enter else None
        render_hover_frame()

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
                            messagebox.showinfo("DEV MODE", tr("🔓 Инициализация разработчика...\n\nDEV Режим разблокирован!"))
            else:
                open_config_screen(scan_code)
        return on_numpad_click

    _first_place = {"done": False}
    def draw_numpad():
        canvas_numpad.delete("all")
        apply_native_style()
        dev = MACRO_CONFIG.get("DevSettings", {})
        labels_var.set(MACRO_CONFIG["AppSettings"].get("show_labels", True))
        
        win_w = WIN_W
        win_h = WIN_H
        if not _first_place["done"]:
            _first_place["done"] = True
            sw, sh = ui_root.winfo_screenwidth(), ui_root.winfo_screenheight()
            ui_root.geometry(f"{win_w}x{win_h}+{max(0, (sw - win_w) // 2)}+{max(0, (sh - win_h) // 2)}")
        else:
            ui_root.geometry(f"{win_w}x{win_h}")
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
        tk.Label(controls_sub_fr, text=tr("Названия кнопок"), bg=dev.get("theme_grad_top", "#2a2a2a"), fg="#888888", font=("Segoe UI", 9)).pack(side=tk.RIGHT)
        
        # --- ОТРИСОВКА КНОПОК ---
        BASE_SIZE = dev.get("base_size", 81)
        SPACING = dev.get("spacing", 79)
        SCALE = dev.get("scale", 1.11)
        
        grid_w = 3 * SPACING + BASE_SIZE
        grid_h = 4 * SPACING + BASE_SIZE
        START_X = (win_w - grid_w) / 2
        START_Y = max(110, (win_h - grid_h) / 2 - 10) 
        
        show_lbls = MACRO_CONFIG["AppSettings"].get("show_labels", True)
        color_active = dev.get("color_active", "#1db954")
        color_inactive = dev.get("color_inactive", "#3a3a3a")
        
        for btn in NUMPAD_LAYOUT:
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
            
            rect_id = canvas_numpad.create_image(center_x, center_y, image=btn_img_cache.get(cache_key)) if cache_key in btn_img_cache else canvas_numpad.create_polygon([x1+15,y1, x1+draw_w-15,y1, x1+draw_w,y1+15, x1+draw_w,y1+draw_h-15, x1+draw_w-15,y1+draw_h, x1+15,y1+draw_h, x1,y1+draw_h-15, x1,y1+15], smooth=True, fill=color)
            
            if sc == "69": t_x, t_y, t_s = dev.get("text_x_nlk", 29), dev.get("text_y_nlk", 21), int(dev.get("text_size_nlk", 12))
            elif sc == "284": t_x, t_y, t_s = dev.get("text_x_ent", 29), dev.get("text_y_ent", 21), int(dev.get("text_size_ent", 12))
            else: t_x, t_y, t_s = dev.get("text_x", 29), dev.get("text_y", 21), int(dev.get("text_size", 12))
            
            btn_geom_cache[sc] = {"w": draw_w, "h": draw_h, "cx": center_x, "cy": center_y, "cs": col_span, "rs": row_span, "color": color, "is_act": is_active, "t_x": t_x, "t_y": t_y, "t_size": t_s}
            
            def bind_btn(r_id, s=sc):
                if locked:
                    canvas_numpad.tag_bind(r_id, "<Enter>", lambda e: canvas_numpad.config(cursor="no"))
                    canvas_numpad.tag_bind(r_id, "<Leave>", lambda e: canvas_numpad.config(cursor=""))
                    return
                canvas_numpad.tag_bind(r_id, "<Button-1>", make_click_handler(s))
                canvas_numpad.tag_bind(r_id, "<Enter>", lambda e, cur=s: [canvas_numpad.config(cursor="hand2"), trigger_hover(cur, True)])
                canvas_numpad.tag_bind(r_id, "<Leave>", lambda e, cur=s: [canvas_numpad.config(cursor=""), trigger_hover(cur, False)])
            bind_btn(rect_id)

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
                        canvas_numpad.create_image(center_x, center_y, image=btn_img_cache[ik_key], tags="hover_fx", state="disabled")
                        drawn_icon = True

            if show_lbls and not drawn_icon:
                lbl_text = SC_NAMES.get(sc, sc)
                txt_color = "#ffffff" if is_active else ("#5f5f5f" if locked else "#888888")
                canvas_numpad.create_text((center_x - draw_w/2) + t_x*SCALE, (center_y - draw_h/2) + t_y*SCALE, text=lbl_text, fill=txt_color, font=("Segoe UI", int(t_s*SCALE), "bold"), anchor="nw")

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

    lbl_overlay_tip = tk.Label(config_content, text=tr("💡 ОВЕРЛЕЙ\n\nКороткое нажатие — Вкл/Выкл\nУдержание (Hold) — Открыть студию настройки"), fg="#f5d142", bg="#1e1e1e", font=("Segoe UI", 10, "bold"), justify=tk.CENTER)

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
        RoundBtn(top, text=tr("Закрыть"), bg="#3a3a3a", fg="#fff", font=("Segoe UI", 9), borderwidth=0, cursor="hand2", command=top.destroy).pack(side=tk.BOTTOM, pady=10, ipadx=10, ipady=4)

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
                top.title(tr("Выбор"))
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
        
    def create_color_row(parent, label_text, var):
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
        tk.Label(row, textvariable=var, fg="#aaaaaa", bg=_bg, font=("Consolas", 9)).pack(side=tk.RIGHT)
        return row

    var_type = tk.StringVar()
    var_lang = tk.StringVar()
    var_path = tk.StringVar()
    var_proc = tk.StringVar()
    var_act = tk.StringVar()
    var_sec = tk.StringVar()
    var_admin_bool = tk.BooleanVar()
    var_vol_dir = tk.StringVar()
    var_vol_pair = tk.StringVar()
    _VT_PROC, _VT_ACTIVE, _VT_SYSTEM = tr("Процесс (поле Process)"), tr("Активное приложение"), tr("Вся система")
    _VT_CODES = {_VT_PROC: "process", _VT_ACTIVE: "active", _VT_SYSTEM: "system"}
    var_vol_target = tk.StringVar(value=_VT_PROC)
    var_icon_path = tk.StringVar()
    var_icon_color = tk.StringVar()

    row_type = create_dropdown_row(config_content, "Type", var_type, type_options(), tr("Выбор основного действия."), tr("Определяет, что будет делать кнопка."), lambda e: refresh_config_ui())
    row_lang = create_dropdown_row(config_content, "Language", var_lang, ["ENG", "RUS", "DE"], tr("Язык переключения."), tr("Выберите язык из списка."))
    row_path = create_input_row(config_content, "Path", var_path, tr("Путь до файла."), tr("Укажите абсолютный путь до файла программы."), browse_type="file")
    row_proc = create_input_row(config_content, "Process", var_proc, tr("Имя процесса в диспетчере."), tr("Точное имя процесса (например, spotify.exe)."), browse_type="process")
    row_act = create_input_row(config_content, "ActionTime", var_act, tr("Задержка перед срабатыванием (сек)."), tr("Укажите 0 для моментального срабатывания при клике."))
    row_sec = create_input_row(config_content, "Hold To Action", var_sec, tr("Долгое удержание (сек)."), tr("Время удержания для второго действия. Укажите 1.0 для оверлея."))
    row_admin = create_switch_row(config_content, "Run as Admin", var_admin_bool, tr("Запуск от имени Админа."), tr("Программа будет запущена с максимальными правами в Windows."))
    row_voltarget = create_dropdown_row(config_content, tr("Цель"), var_vol_target, [_VT_PROC, _VT_ACTIVE, _VT_SYSTEM], tr("Чьей громкостью управлять."), tr("Процесс — приложение из поля Process (например, Spotify).\n\nАктивное приложение — то, окно которого сейчас на переднем плане (звук берётся и у его дочерних процессов, например у браузера).\n\nВся система — общая громкость Windows. Лимит из настроек ниже действует и здесь: поставьте 100, чтобы он не мешал."), lambda e: refresh_config_ui())
    row_voldir = create_dropdown_row(config_content, "Direction", var_vol_dir, ["Up (+)", "Down (-)"], tr("Направление регулировки звука."), tr("Up: Увеличивает громкость.\nDown: Уменьшает громкость."))
    row_volpair = create_dropdown_row(config_content, "Pair Button", var_vol_pair, [tr("Нет")], tr("Авто-настройка второй кнопки."), tr("Позволяет сразу назначить обратное действие на другую кнопку."))
    row_icon_path = create_input_row(config_content, "Icon Path", var_icon_path, tr("Путь до иконки"), tr("Укажите путь до картинки (png/jpg)."), browse_type="file")
    row_icon_color = create_color_row(config_content, "Icon Color", var_icon_color)

    # --- Прицел и лёгкий макрос: поля настройки ---
    _CH_MODE_TOGGLE = tr("Вкл/Выкл")
    _CH_MODE_SMART = tr("Умный (удержание + смена)")
    var_ch_mode = tk.StringVar(value=_CH_MODE_TOGGLE)
    var_ch_name = tk.StringVar()
    ch_sel = []
    hotkey_list = []
    row_ch_mode = create_dropdown_row(config_content, tr("Режим прицела"), var_ch_mode, [_CH_MODE_TOGGLE, _CH_MODE_SMART], tr("Как кнопка управляет прицелом."), tr("Вкл/Выкл — нажатие показывает или скрывает выбранный прицел.\n\nУмный — удержание показывает/скрывает прицел, короткое нажатие переключает на следующий из списка."), lambda e: refresh_config_ui())
    row_ch_name = create_dropdown_row(config_content, tr("Прицел"), var_ch_name, [], tr("Какой прицел показывать."), tr("Прицелы создаются в конструкторе: Настройки → Открыть конструктор прицелов."))
    lbl_ch_tip = tk.Label(config_content, text="", fg="#f5d142", bg="#1e1e1e", font=("Segoe UI", 10, "bold"), justify=tk.CENTER)
    ch_list_container = tk.Frame(config_content)
    row_hotkey = tk.Frame(config_content)

    def _cfg_bg():
        return MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020")

    def render_ch_list():
        bg = _cfg_bg()
        ch_list_container.config(bg=bg)
        for w in ch_list_container.winfo_children(): w.destroy()
        tk.Label(ch_list_container, text=tr("Прицелы в ротации (порядок — по очерёдности выбора)"), fg="#999999", bg=bg, font=("Segoe UI", 10, "bold"), anchor="w").pack(fill=tk.X, padx=30, pady=(5, 5))
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
        tk.Label(row_hotkey, text=tr("Комбинация клавиш"), fg="#e8e8e8", bg=bg, font=("Segoe UI", 10), anchor="w").pack(fill=tk.X, padx=30, pady=(8, 4))
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
            tk.Label(row_hotkey, text=tr("Нажмите «＋» и выберите клавишу на экранной клавиатуре. Клавиши нажимаются по порядку и отпускаются в обратном."), fg="#777777", bg=bg, font=("Segoe UI", 9), justify=tk.LEFT, wraplength=max(220, avail)).pack(fill=tk.X, padx=30, pady=(2, 8))
        config_content.update_idletasks()
        config_canvas.configure(scrollregion=config_canvas.bbox("all"))

    _bg_cfg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
    sound_container = tk.Frame(config_content, bg=_bg_cfg)
    tk.Label(sound_container, text=tr("Настройки звука процесса"), fg="#999999", bg=_bg_cfg, font=("Segoe UI", 11, "bold")).pack(pady=(15, 5), anchor="w", padx=30)
    
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

    create_embedded_slider(sound_container, tr("Лимит громкости %"), "limit", 10, 100)
    tk.Label(sound_container, text=tr("Тихая зона"), fg="#1db954", bg=_bg_cfg, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=30, pady=(10,0))
    create_embedded_slider(sound_container, tr("Порог до (%)"), "low_thresh", 1, 100)
    create_embedded_slider(sound_container, tr("Шаг (%)"), "low_step", 1, 20)
    create_embedded_slider(sound_container, tr("Задержка (мс)"), "low_delay", 10, 500)
    tk.Label(sound_container, text=tr("Средняя зона"), fg="#1db954", bg=_bg_cfg, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=30, pady=(10,0))
    create_embedded_slider(sound_container, tr("Порог до (%)"), "mid_thresh", 1, 100)
    create_embedded_slider(sound_container, tr("Шаг (%)"), "mid_step", 1, 20)
    create_embedded_slider(sound_container, tr("Задержка (мс)"), "mid_delay", 10, 500)
    tk.Label(sound_container, text=tr("Громкая зона"), fg="#1db954", bg=_bg_cfg, font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=30, pady=(10,0))
    create_embedded_slider(sound_container, tr("Шаг (%)"), "high_step", 1, 20)
    create_embedded_slider(sound_container, tr("Задержка (мс)"), "high_delay", 10, 500)

    def refresh_config_ui(*args):
        t = label_to_type(var_type.get())
        for r in [row_lang, row_path, row_proc, row_act, row_sec, row_admin, row_voltarget, row_voldir, row_volpair, sound_container, lbl_overlay_tip, row_ch_mode, row_ch_name, ch_list_container, lbl_ch_tip, row_hotkey]: r.pack_forget()
        
        row_icon_path.pack(fill=tk.X, padx=30, pady=2)
        row_icon_color.pack(fill=tk.X, padx=30, pady=2)
            
        if t == "exec":
            for r in [row_path, row_proc, row_act, row_sec, row_admin]: r.pack(fill=tk.X, padx=30, pady=2)
        elif t == "lang": row_lang.pack(fill=tk.X, padx=30, pady=2)
        elif t == "volume":
            row_voltarget.pack(fill=tk.X, padx=30, pady=2)
            row_voldir.pack(fill=tk.X, padx=30, pady=2)
            if var_vol_target.get() == _VT_PROC: row_proc.pack(fill=tk.X, padx=30, pady=2)
            row_volpair.pack(fill=tk.X, padx=30, pady=2)
            sound_container.pack(fill=tk.X, pady=(10, 5))
        elif t == "restart": row_act.pack(fill=tk.X, padx=30, pady=2)
        elif t == "overlay":
            lbl_overlay_tip.pack(fill=tk.X, pady=(10, 20))
            if float(var_sec.get() or -1) <= 0: var_sec.set("1.0")
            if float(var_act.get() or -1) < 0: var_act.set("0.0")
            row_act.pack(fill=tk.X, padx=30, pady=2)
            row_sec.pack(fill=tk.X, padx=30, pady=2)
        elif t == "crosshair":
            smart = var_ch_mode.get() == _CH_MODE_SMART
            lbl_ch_tip.config(text=(tr("💡 ПРИЦЕЛ\n\nУдержание — показать/скрыть\nНажатие — следующий прицел из списка") if smart else tr("💡 ПРИЦЕЛ\n\nНажатие — показать/скрыть выбранный прицел")))
            lbl_ch_tip.pack(fill=tk.X, pady=(10, 10))
            row_ch_mode.pack(fill=tk.X, padx=30, pady=2)
            if smart:
                render_ch_list()
                ch_list_container.pack(fill=tk.X, pady=(5, 5))
                try: need_sec = float(var_sec.get() or -1) <= 0
                except ValueError: need_sec = True
                if need_sec: var_sec.set("0.5")
                row_sec.pack(fill=tk.X, padx=30, pady=2)
            else:
                row_ch_name.pack(fill=tk.X, padx=30, pady=2)
        elif t == "light macro":
            render_hotkey_chips()
            row_hotkey.pack(fill=tk.X, pady=(5, 5))
            
        config_content.update_idletasks()
        config_canvas.configure(scrollregion=config_canvas.bbox("all"))

    def save_button_click():
        if not current_edit_sc: return
        t = label_to_type(var_type.get())
        vd = 1 if var_vol_dir.get() == "Up (+)" else -1
        
        aud_cfg = {k: v.get() for k, v in audio_vars.items()}
        current_overlay = MACRO_CONFIG.get(current_edit_sc, {}).get("Overlay", MACRO_TEMPLATE["Overlay"].copy())
        
        act_save = 0.0 if t in ("crosshair", "light macro") else float(var_act.get() or 0)
        sec_save = float(var_sec.get() or -1)
        if t == "light macro": sec_save = -1.0
        if t == "crosshair": sec_save = max(0.1, sec_save) if var_ch_mode.get() == _CH_MODE_SMART else -1.0
        
        MACRO_CONFIG[current_edit_sc] = {
            "Type": t,
            "Language": var_lang.get() if t == "lang" else "-1",
            "Path": var_path.get() if t == "exec" else "-1",
            "ProcessName": var_proc.get() if t in ["exec", "volume"] else "-1",
            "ActionTime": act_save,
            "SecondActionTime": sec_save,
            "AdminRights": 1 if var_admin_bool.get() else 0,
            "VolumeDirection": vd if t == "volume" else 1,
            "VolumeTarget": _VT_CODES.get(var_vol_target.get(), "process"),
            "Desc": f"Macro SC {current_edit_sc}",
            "IconPath": var_icon_path.get(),
            "IconColor": var_icon_color.get(),
            "Audio": aud_cfg.copy(),
            "Overlay": current_overlay,
            "Crosshair": {"mode": "smart" if var_ch_mode.get() == _CH_MODE_SMART else "toggle", "name": var_ch_name.get(), "list": list(ch_sel)},
            "Hotkey": list(hotkey_list)
        }
        
        if t == "volume" and var_vol_pair.get() != tr("Нет"):
            pair_name = var_vol_pair.get()
            pair_sc = next((k for k, v in SC_NAMES.items() if v == pair_name), None)
            if pair_sc:
                MACRO_CONFIG[pair_sc] = {
                    "Type": "volume", "Language": "-1", "Path": "-1",
                    "ProcessName": var_proc.get(), "ActionTime": 0.0, "SecondActionTime": -1.0,
                    "AdminRights": 0, "VolumeDirection": -vd, "VolumeTarget": _VT_CODES.get(var_vol_target.get(), "process"), "Desc": f"Pair for {current_edit_sc}",
                    "IconPath": var_icon_path.get(),
                    "IconColor": var_icon_color.get(),
                    "Audio": aud_cfg.copy(),
                    "Overlay": MACRO_TEMPLATE["Overlay"].copy()
                }
                
        save_config()
        show_main_screen()

    config_bottom_fr = tk.Frame(config_content, bg=MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111"))
    config_bottom_fr.pack(pady=30, fill=tk.X, padx=30)
    RoundBtn(config_bottom_fr, text=tr("Назад"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11), borderwidth=0, cursor="hand2", command=lambda: show_main_screen()).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), ipady=6)
    RoundBtn(config_bottom_fr, text=tr("Сохранить"), bg="#1db954", fg="#ffffff", font=("Segoe UI", 11, "bold"), borderwidth=0, cursor="hand2", command=save_button_click).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(5, 0), ipady=6)


    # ================= КОНСТРУКТОР ПРИЦЕЛОВ =================
    def open_crosshair_designer():
        for w in crosshair_content.winfo_children(): w.destroy()
        settings_bg_frame.place_forget()
        config_bg_frame.place_forget()
        _ensure_dark_combobox_style()

        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#202020")
        default_name = "По умолчанию"
        presets = MACRO_CONFIG.setdefault("Crosshairs", {})
        if default_name not in presets:
            presets[default_name] = dict(DEFAULT_CONFIG["Crosshairs"][default_name])
        ch = dict(DEFAULT_CONFIG["Crosshairs"][default_name])
        ch.update(presets[default_name])

        shape_names = {"cross": tr("Крест"), "t": tr("Т-образный"), "circle": tr("Круг"), "dot": tr("Точка")}
        shape_codes = {v: k for k, v in shape_names.items()}

        def section(text, top=15):
            tk.Label(crosshair_content, text=text, fg="#999999", bg=_bg, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=30, pady=(top, 0))

        tk.Label(crosshair_content, text=tr("Конструктор прицела"), fg="#ffffff", bg=_bg, font=("Segoe UI", 16, "bold")).pack(anchor="w", padx=30, pady=(20, 10))

        # --- предпросмотр на разных фонах ---
        PREVIEW = 100
        preview_bgs = [(tr("Светлый"), "#d9d9d9"), (tr("Тёмный"), "#141414"), (tr("Пёстрый"), None)]
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
        section(tr("1. Форма и геометрия"), top=5)
        shape_var = tk.StringVar(value=shape_names.get(ch.get("shape", "cross"), tr("Крест")))
        def on_shape(e=None):
            ch["shape"] = shape_codes.get(shape_var.get(), "cross")
            refresh_preview()
        create_dropdown_row(crosshair_content, tr("Тип прицела"), shape_var, list(shape_codes.keys()), command=on_shape)

        dot_var = tk.BooleanVar(value=bool(ch.get("center_dot", True)))
        def on_dot():
            ch["center_dot"] = dot_var.get()
            refresh_preview()
        create_switch_row(crosshair_content, tr("Точка в центре"), dot_var, command=on_dot)

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

        add_slider(tr("Размер точки (px)"), "dot_size", 1, 10)
        add_slider(tr("Длина линий (px)"), "line_length", 0, 50)
        add_slider(tr("Толщина линий (px)"), "line_thickness", 1, 10)
        add_slider(tr("Зазор / отступ (px)"), "gap", -20, 30)
        add_slider(tr("Угол поворота (°)"), "rotation", 0, 360)

        # --- 2. цвет и прозрачность ---
        section(tr("2. Цвет и прозрачность"))
        color_var = tk.StringVar(value=ch.get("color", "#1db954"))
        create_color_row(crosshair_content, tr("Цвет прицела"), color_var)
        def on_color(*_):
            ch["color"] = color_var.get(); refresh_preview()
        color_var.trace_add("write", on_color)
        sw_row = tk.Frame(crosshair_content, bg=_bg); sw_row.pack(fill=tk.X, padx=30, pady=(0, 5))
        for sw_hex in ("#1db954", "#00e5ff", "#ffee00", "#ff2d95", "#ffffff"):
            RoundBtn(sw_row, bg=sw_hex, activebackground=sw_hex, width=3, borderwidth=0, cursor="hand2", command=lambda c=sw_hex: color_var.set(c)).pack(side=tk.LEFT, padx=3)
        add_slider(tr("Прозрачность (%)"), "opacity", 0, 100)

        # --- 3. обводка ---
        section(tr("3. Обводка"))
        outline_var = tk.BooleanVar(value=bool(ch.get("outline_enabled", True)))
        def on_outline():
            ch["outline_enabled"] = outline_var.get(); refresh_preview()
        create_switch_row(crosshair_content, tr("Включить обводку"), outline_var, command=on_outline)
        add_slider(tr("Толщина обводки (px)"), "outline_thickness", 1, 5)
        out_color_var = tk.StringVar(value=ch.get("outline_color", "#000000"))
        create_color_row(crosshair_content, tr("Цвет обводки"), out_color_var)
        def on_out_color(*_):
            ch["outline_color"] = out_color_var.get(); refresh_preview()
        out_color_var.trace_add("write", on_out_color)
        add_slider(tr("Прозрачность обводки (%)"), "outline_opacity", 0, 100)

        # --- сохранённые прицелы ---
        section(tr("Сохранённые прицелы"), top=20)
        name_var = tk.StringVar(value=default_name)
        name_row = tk.Frame(crosshair_content, bg=_bg); name_row.pack(fill=tk.X, padx=30, pady=8)
        tk.Label(name_row, text=tr("Имя"), fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        tk.Entry(name_row, textvariable=name_var, bg="#2d2d2d", fg="#ffffff", insertbackground="#ffffff", borderwidth=0, font=("Segoe UI", 10)).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0), ipady=5)

        load_var = tk.StringVar(value=default_name)
        load_row = tk.Frame(crosshair_content, bg=_bg); load_row.pack(fill=tk.X, padx=30, pady=8)
        tk.Label(load_row, text=tr("Выбрать сохранённый"), fg="#e8e8e8", bg=_bg, font=("Segoe UI", 10)).pack(side=tk.LEFT)
        load_combo = ttk.Combobox(load_row, textvariable=load_var, state="readonly", font=("Segoe UI", 10), style="Dark.TCombobox")
        load_combo.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0), ipady=2)

        def refresh_names():
            names = list(MACRO_CONFIG.get("Crosshairs", {}).keys())
            load_combo["values"] = names
            if names and load_var.get() not in names: load_var.set(names[0])

        def populate(params):
            base = dict(DEFAULT_CONFIG["Crosshairs"][default_name]); base.update(params)
            ch.clear(); ch.update(base)
            shape_var.set(shape_names.get(ch.get("shape", "cross"), tr("Крест")))
            dot_var.set(bool(ch["center_dot"])); outline_var.set(bool(ch["outline_enabled"]))
            color_var.set(ch["color"]); out_color_var.set(ch["outline_color"])
            for k, (sl, lbl) in sliders.items():
                sl.set(ch[k]); lbl.config(text=str(int(ch[k])))
            refresh_preview()

        def do_save():
            nm = name_var.get().strip()
            if not nm:
                messagebox.showerror(tr("Прицел"), tr("Введите имя прицела.")); return
            MACRO_CONFIG.setdefault("Crosshairs", {})[nm] = dict(ch)
            save_config(); refresh_names(); load_var.set(nm)
            messagebox.showinfo(tr("Прицел"), tr("Прицел «{}» сохранён.").format(nm))

        def do_load():
            nm = load_var.get()
            preset = MACRO_CONFIG.get("Crosshairs", {}).get(nm)
            if not preset:
                messagebox.showerror(tr("Прицел"), tr("Такой прицел не найден.")); return
            name_var.set(nm); populate(preset)

        def do_delete():
            nm = load_var.get()
            if nm == default_name:
                messagebox.showerror(tr("Прицел"), tr("Прицел по умолчанию удалить нельзя.")); return
            if nm in MACRO_CONFIG.get("Crosshairs", {}) and messagebox.askyesno(tr("Прицел"), tr("Удалить прицел «{}»?").format(nm)):
                del MACRO_CONFIG["Crosshairs"][nm]
                save_config(); refresh_names()

        btn_row = tk.Frame(crosshair_content, bg=_bg); btn_row.pack(fill=tk.X, padx=30, pady=5)
        RoundBtn(btn_row, text=tr("Сохранить"), bg="#1db954", fg="#000000", font=("Segoe UI", 10, "bold"), borderwidth=0, cursor="hand2", command=do_save).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3), ipady=6)
        RoundBtn(btn_row, text=tr("Загрузить"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=do_load).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=3, ipady=6)
        RoundBtn(btn_row, text=tr("Удалить"), bg="#3a2020", fg="#ff8080", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=do_delete).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0), ipady=6)
        refresh_names()

        # --- код прицела ---
        section(tr("Код прицела"), top=20)
        def do_copy_code():
            try:
                pyperclip.copy(encode_crosshair_code(ch))
                messagebox.showinfo(tr("Прицел"), tr("Код скопирован в буфер обмена."))
            except Exception:
                messagebox.showerror(tr("Прицел"), tr("Не удалось скопировать код."))
        RoundBtn(crosshair_content, text=tr("Скопировать код"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=do_copy_code).pack(fill=tk.X, padx=30, pady=5, ipady=6)

        code_var = tk.StringVar()
        def do_apply_code():
            try:
                params = decode_crosshair_code(code_var.get())
                if not isinstance(params, dict): raise ValueError
                populate(params)
            except Exception:
                messagebox.showerror(tr("Прицел"), tr("Неверный или повреждённый код прицела."))
        code_row = tk.Frame(crosshair_content, bg=_bg); code_row.pack(fill=tk.X, padx=30, pady=5)
        tk.Entry(code_row, textvariable=code_var, bg="#2d2d2d", fg="#ffffff", insertbackground="#ffffff", borderwidth=0, font=("Segoe UI", 9)).pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)
        RoundBtn(code_row, text=tr("Применить код"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=do_apply_code).pack(side=tk.RIGHT, padx=(10, 0), ipadx=5, ipady=4)

        RoundBtn(crosshair_content, text=tr("Сбросить к значениям по умолчанию"), bg="#3a3a3a", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=lambda: populate(DEFAULT_CONFIG["Crosshairs"][default_name])).pack(fill=tk.X, padx=30, pady=(10, 5), ipady=6)
        RoundBtn(crosshair_content, text=tr("Назад"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 11), borderwidth=0, cursor="hand2", command=lambda: show_main_screen()).pack(fill=tk.X, padx=30, pady=20, ipady=6)

        refresh_preview()
        dev = MACRO_CONFIG.get("DevSettings", {})
        win_w, win_h = WIN_W, WIN_H
        pad = 14
        crosshair_bg_frame.place(x=pad, y=pad, width=win_w-pad*2, height=win_h-pad*2)
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
        top.title(tr("Выбор клавиши"))
        top.configure(bg="#202020")
        top.attributes("-topmost", True)
        top.resizable(False, False)
        U = 36
        W, H = int(23.2 * U) + 30, int(9.6 * U) + 110
        sw, sh = ui_root.winfo_screenwidth(), ui_root.winfo_screenheight()
        top.geometry(f"{W}x{H}+{max(0, (sw - W) // 2)}+{max(0, (sh - H) // 2)}")
        tk.Label(top, text=tr("Нажмите на клавишу, чтобы добавить её в комбинацию"), fg="#e8e8e8", bg="#202020", font=("Segoe UI", 11)).pack(pady=(12, 6))
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
        RoundBtn(top, text=tr("Отмена"), bg="#2d2d2d", fg="#ffffff", font=("Segoe UI", 10), borderwidth=0, cursor="hand2", command=top.destroy).pack(pady=(0, 12), ipadx=24, ipady=4)

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
            show_osd(tr("Прицел не найден"))
            return False
        hide_crosshair()
        base = dict(DEFAULT_CONFIG["Crosshairs"]["По умолчанию"]); base.update(params)
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
                show_osd(tr("Прицел: список пуст"))
                return
            idx = ch_idx.get(sc, 0) % len(names)
            if is_second:
                if crosshair_state["win"] is not None:
                    hide_crosshair(); show_osd(tr("Прицел ВЫКЛ"))
                elif show_crosshair(names[idx]):
                    ch_idx[sc] = idx; show_osd(tr("Прицел: {}").format(names[idx]))
            else:
                idx = (idx + 1) % len(names)
                ch_idx[sc] = idx
                if crosshair_state["win"] is not None: show_crosshair(names[idx])
                show_osd(tr("Прицел: {}").format(names[idx]))
        else:
            nm = cr.get("name") or next(iter(presets), "")
            if crosshair_state["win"] is not None and crosshair_state["name"] == nm:
                hide_crosshair(); show_osd(tr("Прицел ВЫКЛ"))
            elif show_crosshair(nm):
                show_osd(tr("Прицел: {}").format(nm))

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
        settings_bg_frame.place(x=pad, y=pad, width=win_w-pad*2, height=win_h-pad*2)
        settings_bg_frame.lift()

    def open_config_screen(sc):
        global current_edit_sc
        current_edit_sc = str(sc)
        cfg = MACRO_CONFIG.get(current_edit_sc, MACRO_TEMPLATE.copy())
        
        key_name = SC_NAMES.get(current_edit_sc, f"NUM_{current_edit_sc}")
        
        _bg = MACRO_CONFIG.get("DevSettings", {}).get("theme_grad_bot", "#111111")
        config_canvas.config(bg=_bg)
        config_content.config(bg=_bg)
        config_title.config(text=tr("Настройка {}").format(key_name), bg=_bg)
        lbl_overlay_tip.config(bg=_bg)
        lbl_ch_tip.config(bg=_bg)
        
        for r in [row_type, row_lang, row_path, row_proc, row_act, row_sec, row_admin, row_voldir, row_volpair, row_voltarget, row_icon_path, row_icon_color, row_ch_mode, row_ch_name, config_bottom_fr]:
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
        var_admin_bool.set(True if cfg.get("AdminRights") == 1 else False)
        var_vol_dir.set("Up (+)" if cfg.get("VolumeDirection", 1) == 1 else "Down (-)")
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
        
        opts = [tr("Нет")] + [SC_NAMES[k] for k in SC_NAMES if k != current_edit_sc]
        row_volpair.winfo_children()[1].configure(values=opts)
        var_vol_pair.set(tr("Нет"))
        
        refresh_config_ui()
        settings_bg_frame.place_forget()
        crosshair_bg_frame.place_forget()
        
        dev = MACRO_CONFIG.get("DevSettings", {})
        win_w, win_h = WIN_W, WIN_H
        pad = 14
        
        config_bg_frame.place(x=pad, y=pad, width=win_w-pad*2, height=win_h-pad*2)
        config_bg_frame.lift()

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
            _osd_show(render_osd_image(tr("ПРЕВЬЮ 65%"), None, False, 0.65, scale), auto_hide=False)
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
    # системный MCI; каждое срабатывание берёт свободный "канал" из пула, поэтому
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

    menu = pystray.Menu(item(tr('Настройки'), tray_show_ui, default=True), item(tr('Выход'), tray_quit))
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
            if not force_show: show_osd(tr("Оверлей: Нет картинки")); return
            
        win = tk.Toplevel(ui_root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#000000")
        win.wm_attributes("-transparentcolor", "#000000")
        
        label = tk.Label(win, bg="#000000")
        label.pack(fill=tk.BOTH, expand=True)
        
        def start_drag(e):
            if cfg.get("interactive", True): win.x, win.y = e.x, e.y
        def do_drag(e):
            if cfg.get("interactive", True):
                new_x, new_y = win.winfo_x() + e.x - win.x, win.winfo_y() + e.y - win.y
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
        if not force_show: show_osd(tr("Оверлей ВКЛ"))

    def open_overlay_settings(sc):
        cfg = MACRO_CONFIG[sc].setdefault("Overlay", MACRO_TEMPLATE["Overlay"].copy())
        
        top = tk.Toplevel(ui_root)
        top.title(tr("Студия Оверлея"))
        top.geometry("380x580")
        top.attributes("-topmost", True)
        top.configure(bg="#1e1e1e")
        
        tk.Label(top, text=tr("СТУДИЯ ОВЕРЛЕЯ"), fg="#1db954", bg="#1e1e1e", font=("Consolas", 14, "bold")).pack(pady=(15, 10))
        
        toggle_overlay(sc, force_show=True)
        
        def redraw(*args):
            if sc in active_overlays: refresh_overlay(sc)
            
        fr_path = tk.Frame(top, bg="#1e1e1e"); fr_path.pack(fill=tk.X, padx=20, pady=5)
        tk.Label(fr_path, text=tr("Картинка:"), fg="#ccc", bg="#1e1e1e").pack(side=tk.LEFT)
        btn_path = RoundBtn(fr_path, text=tr("Выбрать..."), bg="#333", fg="#fff", bd=0, cursor="hand2")
        btn_path.pack(side=tk.RIGHT)
        lbl_path = tk.Label(top, text=os.path.basename(cfg["path"]) or tr("Не выбрано"), fg="#888", bg="#1e1e1e")
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
        var_x = add_slider(tr("Позиция X"), "x", 0, sw)
        var_y = add_slider(tr("Позиция Y"), "y", 0, sh)
        var_w = add_slider(tr("Ширина"), "w", 10, sw*2)
        var_h = add_slider(tr("Высота"), "h", 10, sh*2)
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
        tk.Checkbutton(fr_check1, text=tr("Пропорции"), variable=var_lock, bg="#1e1e1e", fg="#ccc", selectcolor="#333", activebackground="#1e1e1e", command=lambda: cfg.update({"lock_aspect": var_lock.get()})).pack(side=tk.LEFT)
        tk.Checkbutton(fr_check1, text=tr("Интерактивное"), variable=var_interactive, bg="#1e1e1e", fg="#ccc", selectcolor="#333", activebackground="#1e1e1e", command=update_interactive).pack(side=tk.RIGHT)

        fr_check2 = tk.Frame(top, bg="#1e1e1e"); fr_check2.pack(fill=tk.X, padx=20, pady=(0,0))
        tk.Checkbutton(fr_check2, text=tr("Сглаживание"), variable=var_smooth, bg="#1e1e1e", fg="#ccc", selectcolor="#333", activebackground="#1e1e1e", command=update_render_opts).pack(side=tk.LEFT)
        tk.Checkbutton(fr_check2, text=tr("Резкие края (Alpha)"), variable=var_fix_alpha, bg="#1e1e1e", fg="#ccc", selectcolor="#333", activebackground="#1e1e1e", command=update_render_opts).pack(side=tk.RIGHT)

        fr_blend = tk.Frame(top, bg="#1e1e1e"); fr_blend.pack(fill=tk.X, padx=20, pady=(5,0))
        tk.Label(fr_blend, text=tr("Наложение:"), fg="#ccc", bg="#1e1e1e").pack(side=tk.LEFT)
        
        def on_blend_change(*args):
            b_val = var_blend.get()
            b_map = {tr("Обычное (Black Key)"): "black", tr("Светлое (White Key)"): "white", tr("Хромакей (Magenta)"): "magenta"}
            cfg["blend"] = b_map.get(b_val, "black")
            redraw()
            
        blend_opts = [tr("Обычное (Black Key)"), tr("Светлое (White Key)"), tr("Хромакей (Magenta)")]
        current_blend_str = [k for k, v in {tr("Обычное (Black Key)"): "black", tr("Светлое (White Key)"): "white", tr("Хромакей (Magenta)"): "magenta"}.items() if v == cfg.get("blend", "black")][0]
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
        
        RoundBtn(top, text=tr("ГОТОВО"), bg="#1db954", fg="#fff", font=("Consolas", 12, "bold"), bd=0, cursor="hand2", command=close_editor).pack(side=tk.BOTTOM, fill=tk.X, padx=20, pady=20, ipady=8)

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

    def change_vol(d, target_proc="spotify.exe", mode="process"):
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
                new_v = max(0.0, min(lim, round(curr + (step * d), 3)))
                set_v(new_v)
                prog_disp = new_v / lim if lim > 0 else 0
                pct = f"{int(round(new_v * 100))}%"
                if mode == "system":
                    show_osd(tr("Система: {}").format(pct), progress=prog_disp)
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

    def execute_action(sc, cfg, is_second_action=False):
        t = cfg.get("Type")
        if t and t != "none": play_action_sound()
        if t == "exec":
            path, proc_name, admin = cfg.get("Path"), cfg.get("ProcessName"), cfg.get("AdminRights") == 1
            if is_second_action: manage_app(proc_name, path, action='close')
            else: manage_app(proc_name, path, run_as_user=not admin, action='launch')
        elif t == "lang" and not is_second_action:
            lang_str = cfg.get("Language", "").upper()
            code = {"ENG": 0x04090409, "RUS": 0x04190419, "DE": 0x04070407}.get(lang_str)
            if code:
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                ctypes.windll.user32.PostMessageW(hwnd, 0x0050, 0, code)
                show_osd(tr("🌐 Язык: {}").format(lang_str))
        elif t and t.startswith("mod:") and not is_second_action:
            mid = t[4:]
            m = MODULES.get(mid)
            if not m:
                show_osd(f"✗ module '{mid}' not found")
            else:
                ctx = ModuleContext(mid)
                def _run_module(m=m, cfg=cfg, ctx=ctx):
                    try: m["run"](ctx, cfg)
                    except Exception as e:
                        _runlog(f"MODULE RUN ERROR {ctx.module_id}:\n" + traceback.format_exc())
                        ctx.osd(f"✗ {ctx.module_id}: {e}")
                threading.Thread(target=_run_module, daemon=True).start()
        elif t == "restart" and not is_second_action: restart_script()
        elif t == "dev patch" and not is_second_action: ui_root.after(0, apply_patch_from_clipboard)
        elif t == "overlay":
            if is_second_action: ui_root.after(0, lambda: open_overlay_settings(sc))
            else: ui_root.after(0, lambda: toggle_overlay(sc))
        elif t == "crosshair":
            ui_root.after(0, lambda: crosshair_action(sc, cfg, is_second_action))
        elif t == "light macro" and not is_second_action:
            hk_keys = list(cfg.get("Hotkey", []))
            threading.Thread(target=lambda: send_hotkey(hk_keys), daemon=True).start()

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
                if not vol_thread or not vol_thread.is_alive():
                    vol_thread = threading.Thread(target=volume_repeater, daemon=True); vol_thread.start()
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
                    if not (fl & 0x10) and not (fl & 1) and macro_enabled and str(sc) not in LOCKED_SC and str(sc) in MACRO_CONFIG and MACRO_CONFIG[str(sc)].get("Type") != "none":
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
    _runlog("mainloop start")
    _runlog(f"SOUND FILE: {_find_action_sound()}")
    ui_root.mainloop()
    _runlog("mainloop returned normally")

except BaseException as e:
    _runlog("STARTUP EXCEPTION:\n" + traceback.format_exc())
    ctypes.windll.user32.MessageBoxW(0, _crash_text("Ошибка запуска:", "Startup error:") + f"\n{e}\n\n" + _crash_text("Смотри папку crashlogs", "See the crashlogs folder"), "numbinder Crash", 0x10)