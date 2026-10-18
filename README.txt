numbinder
=========

A Windows app for numpad macros: button overlays, crosshairs, light macros,
a layout fixer, volume control and action sounds.

Language: English or Russian. Switch in Settings (restart required).


1. REQUIREMENTS
---------------
- Windows 10 or 11
- Python 3.10 or newer, 64-bit: https://www.python.org/downloads/
  During installation, tick "Add python.exe to PATH".
  Tkinter is included in the standard installer. Do not untick it.


2. INSTALL
----------
Open the project folder, click the address bar, type "cmd" and press Enter.
Then run:

    python -m pip install -r requirements.txt

This installs: Pillow, pystray, psutil, pyperclip, comtypes, pycaw.


3. FOLDER LAYOUT
----------------
numbinder\
    numbinder.pyw        main program
    requirements.txt     Python packages
    README.txt           this file
    MODULES_GUIDE.txt    how to write modules
    modules\             modules, e.g. layout_fixer.py
    assets\              images and sound
        action1.wav      sound on button press (optional)
        logo.png         app icon
        numpad\          button shapes: single.png, double_hor.png, double_vert.png
        spotify.png ...  button icons (optional)

Your personal settings are stored separately in C:\numbinder\config.json.
Do not share config.json, crashlogs\ or backups\ with other people.


4. RUN
------
Double-click numbinder.pyw.

For debugging, run "python numbinder.pyw" in cmd. Errors are printed in the console.

The app stays in the system tray. Open Settings from the window or the tray menu.


5. LOGS
-------
Each launch writes its own log to C:\numbinder\crashlogs\run_<date>_pid<N>.txt
When reporting a problem, send the newest file from that folder.


6. ACTION SOUND
---------------
Put action1.wav (or .mp4, .mp3, .m4a) into assets\.
Volume and playback target are set in Settings. Without the file, no sound is played.


7. MODULES
----------
Features such as the layout fixer are modules in the modules\ folder.
Install more from Settings -> Modules, or write your own by following MODULES_GUIDE.txt.
Modules run with your account's rights. Install only code you trust.


8. TROUBLESHOOTING
------------------
- Nothing opens on double-click: check the newest file in crashlogs\,
  or run "python numbinder.pyw" in cmd.
- "numbinder is already running": close the other copy first.
- Button shapes are plain green blocks: check that assets\numpad\ exists.
- No sound: check that assets\action1.wav exists and sound is enabled in Settings.
- A module is missing from the Type list: check the modules\ folder. The file must
  define MODULE and run(). See MODULES_GUIDE.txt.
