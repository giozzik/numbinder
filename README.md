# numbinder

**Turn your numpad into a set of smart buttons for Windows.**

numbinder shows a clean on-screen numpad. Press a key and it runs a macro:
open or close an app, control volume or music, fix a typed layout, show a
crosshair, or run your own script from a module.

- Works in the background, sits in the system tray
- Modules you can install or write yourself
- Automatic updates from GitHub, with your permission

---

## Download ↓↓↓

[numbinder latest ver.](https://github.com/giozzik/numbinder/archive/refs/tags/v1.36.0.zip)

that's the latest version, don't forget to read [INSTALL.txt](INSTALL.txt)
or at least drop it in AI and ask it to tell you what to do

All versions: [Releases](https://github.com/giozzik/numbinder/releases)

---

## What a button can do

- **Launch\Close app**: several actions on one key. Press once, press N times
  in a row, or hold for N seconds (the hold time closest to yours wins).
  Actions: launch, close, restart an app, or minimize numbinder to the tray.
- **Volume**: for one app, the active window or the whole system. Smooth or
  step mode. Pair two keys for up and down.
- **Media control**: play/pause, next, previous, stop, mute.
- **Microphone mute**: mutes your mic in all apps at once (Discord, games, calls).
  Toggle, push to talk or push to mute.
- **Switch layout**, **Simple macro** (any key combination),
  **Overlay** (an image on screen), **Crosshair** (made in the built-in designer).
- **clean2;0**: hold to close extra apps, with a keep-open list.
- **Modules** (🧩): for example, the layout fixer for text typed in the wrong layout.

Apps are picked from one list with names and icons, including apps that are
not running yet.

Experimental: **Extended keyboard** (Settings → Experimental) also lets you bind
the F-keys, arrows, Insert…Page Down, Right Alt and Right Ctrl.
Not recommended for everyday use.

## Install in 4 steps

Full step-by-step guide for anyone: **[INSTALL.txt](INSTALL.txt)**

Short version:

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/).
   Tick **"Add python.exe to PATH"**.
2. Download numbinder (link above, or the green **Code** button → **Download ZIP**)
   and unzip it.
3. In the folder, open a terminal and run:
   ```
   python -m pip install -r requirements.txt
   ```
4. Double-click **`numbinder.pyw`**.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer (64-bit)

## Updates

numbinder checks GitHub for new releases. Use **Settings → Check for updates**.
You can turn on **Install updates automatically**, or install them yourself.
Every update is checked with SHA-256 before it is applied, and the previous
version is backed up.

## Modules

Features such as the layout fixer live in the `modules/` folder.
See [modules/MODULES_GUIDE.txt](modules/MODULES_GUIDE.txt) to write your own.
Only install modules whose code you trust.

## Documentation

- [INSTALL.txt](INSTALL.txt): installation for beginners
- [README.txt](README.txt): folder layout, logs, troubleshooting
- [modules/MODULES_GUIDE.txt](modules/MODULES_GUIDE.txt): writing modules

## License

MIT. See [LICENSE](LICENSE).
