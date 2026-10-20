"""
Prepares release files for numbinder.

Run from the folder that contains numbinder.pyw:
    python tools/make_release.py

It reads VERSION and BUILD from numbinder.pyw and writes into the release folder:
    release/numbinder.pyw   the file to attach to the GitHub release
    release/version.json    build number, version and SHA-256 used by the updater
    release/layout_fixer.py and _template.py are copied too, for the release page.
"""
import hashlib
import json
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)            # the folder with numbinder.pyw
SRC = os.path.join(ROOT, "numbinder.pyw")
OUT = os.path.join(ROOT, "release")


def main():
    text = open(SRC, encoding="utf-8").read()
    version = re.search(r'VERSION = "([^"]+)"', text).group(1)
    build = int(re.search(r"BUILD = (\d+)", text).group(1))
    data = open(SRC, "rb").read()
    digest = hashlib.sha256(data).hexdigest()

    os.makedirs(OUT, exist_ok=True)
    shutil.copy2(SRC, os.path.join(OUT, "numbinder.pyw"))
    meta = {"build": build, "version": version, "sha256": digest}
    with open(os.path.join(OUT, "version.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    for name in ("layout_fixer.py", "_template.py"):
        src = os.path.join(ROOT, "modules", name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(OUT, name))

    print(f"Version {version}, build {build}")
    print(f"SHA-256: {digest}")
    print(f"Files are in: {OUT}")
    print("Attach numbinder.pyw and version.json to the GitHub release (tag v" + version.lstrip("v") + ").")


if __name__ == "__main__":
    main()
