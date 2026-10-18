numbinder
=========

Windows app for numpad macros: button overlays, crosshairs, light macros,
layout fixer, volume control and action sounds.
Приложение для Windows: макросы на numpad, оверлеи, прицелы, лёгкие макросы,
исправление раскладки, громкость и звук при срабатывании.

Language / Язык: Russian by default. Switch to English in Settings (restart needed).
                 По умолчанию русский. Переключить на English можно в Настройках (нужен перезапуск).


1. REQUIREMENTS / ТРЕБОВАНИЯ
----------------------------
- Windows 10 or 11 / Windows 10 или 11
- Python 3.10 or newer, 64-bit: https://www.python.org/downloads/
  During installation tick "Add python.exe to PATH".
  При установке отметьте "Add python.exe to PATH".
  Tkinter is included in the standard installer. Do not untick it.
  Tkinter входит в стандартный установщик, его не нужно отключать.


2. INSTALL / УСТАНОВКА
----------------------
Open the project folder, click the address bar, type "cmd" and press Enter.
Откройте папку проекта, в адресной строке введите "cmd" и нажмите Enter.

Then run / Затем выполните:

    python -m pip install -r requirements.txt

This installs: Pillow, pystray, psutil, pyperclip, comtypes, pycaw.


3. FOLDER LAYOUT / СТРУКТУРА ПАПКИ
----------------------------------
numbinder\
    numbinder.pyw        main program / главная программа
    requirements.txt     Python packages / пакеты Python
    README.txt           this file / этот файл
    MODULES_GUIDE.txt    how to write modules / как писать модули
    modules\             modules, e.g. layout_fixer.py / модули, например layout_fixer.py
    assets\              images and sound / картинки и звук
        action1.mp4      sound on button press (optional) / звук при нажатии (необязательно)
        logo.png         app icon / иконка приложения
        numpad\          button shapes: single.png, double_hor.png, double_vert.png
                         формы кнопок: single.png, double_hor.png, double_vert.png
        spotify.png ...  button icons (optional) / иконки кнопок (необязательно)

Your personal config is kept separately in C:\numbinder\config.json.
Личные настройки хранятся отдельно в C:\numbinder\config.json.
Do not send config.json, crashlogs\ or backups\ to other people.
Не отправляйте config.json, crashlogs\ и backups\ другим людям.


4. RUN / ЗАПУСК
---------------
Double-click numbinder.pyw.
Двойной клик по numbinder.pyw.

For debugging, run "python numbinder.pyw" in cmd: errors appear in the console.
Для отладки запустите "python numbinder.pyw" в cmd: ошибки будут видны в консоли.

The app stays in the system tray. Open Settings from the window or the tray menu.
Программа живёт в системном трее. Настройки открываются из окна или меню трея.


5. LOGS / ЛОГИ
--------------
Each launch writes its own log to C:\numbinder\crashlogs\run_<date>_pid<N>.txt
Каждый запуск пишет свой лог в C:\numbinder\crashlogs\run_<дата>_pid<N>.txt
When reporting a problem, send the newest file from that folder.
При жалобе отправляйте самый свежий файл из этой папки.


6. ACTION SOUND / ЗВУК
----------------------
Put action1.mp4 (or .wav, .mp3, .m4a) into assets\.
Положите action1.mp4 (или .wav, .mp3, .m4a) в assets\.
Volume and playback target are set in Settings. Without the file the sound is skipped.
Громкость и цель громкости настраиваются в Настройках. Без файла звук не играет.


7. MODULES / МОДУЛИ
-------------------
Features such as the layout fixer are modules in the modules\ folder.
Функции вроде исправления раскладки — это модули в папке modules\.
Install more in Settings -> Modules, or write your own by following MODULES_GUIDE.txt.
Установить другие можно в Настройки -> Модули, свой — по MODULES_GUIDE.txt.
Modules run with your account's rights. Install only code you trust.
Модули работают с правами вашей учётной записи. Ставьте только код, которому доверяете.


8. TROUBLESHOOTING / ЧАСТЫЕ ПРОБЛЕМЫ
------------------------------------
- Nothing opens on double-click / ничего не открывается:
  check crashlogs\ for the newest file; or run "python numbinder.pyw" in cmd.
  посмотрите свежий файл в crashlogs\ или запустите "python numbinder.pyw" в cmd.
- "numbinder is already running" / "уже запущен": close the other copy first.
  Сначала закройте другую копию.
- Button shapes are plain green blocks / кнопки без формы: check that assets\numpad\ exists.
  Проверьте, что в assets\ есть папка numpad\.
- No sound / нет звука: check assets\action1.mp4 exists and sound is on in Settings.
  Проверьте assets\action1.mp4 и включённый звук в Настройках.
- Module missing from the Type list / модуля нет в списке Тип: check the modules\ folder
  and that the file has MODULE and run(). See MODULES_GUIDE.txt.
  Проверьте папку modules\ и наличие MODULE и run(). См. MODULES_GUIDE.txt.
