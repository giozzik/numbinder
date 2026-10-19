# numbinder

**Turn your numpad into a set of smart buttons for Windows.**

numbinder makes a use of numpad. Press a key and it runs a macro:
open an app, control volume, fix a typed layout, play a sound, or run your
own script from a module.

- Works in the background, sits in the system tray
- Modules you can install or write yourself
- Automatic updates from GitHub, with your permission

---

## Download ↓↓↓

[numbinder latest ver.](https://github.com/giozzik/numbinder/archive/refs/tags/v1.32.0.zip)

that's the latest version, don't forget to read [INSTALL.txt](INSTALL.txt) 
or at least drop it in AI and ask it to tell you what to do

---

## Install in 4 steps

Full step-by-step guide for anyone: **[INSTALL.txt](INSTALL.txt)**

Short version:

1. Install **Python 3.10+** from [python.org](https://www.python.org/downloads/).
   Tick **"Add python.exe to PATH"**.
2. Download this project (green **Code** button → **Download ZIP**) and unzip it.
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
See [MODULES_GUIDE.txt](MODULES_GUIDE.txt) to write your own.
Only install modules whose code you trust.

## Documentation

- [INSTALL.txt](INSTALL.txt): installation for beginners
- [README.txt](README.txt): folder layout, logs, troubleshooting
- [MODULES_GUIDE.txt](MODULES_GUIDE.txt): writing modules

## License

MIT. See [LICENSE](LICENSE).
