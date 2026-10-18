"""
numbinder module TEMPLATE.
Copy this file, rename it (for example, my_module.py) and change the values below.
Files whose names start with "_" are not loaded by numbinder, so this template never runs by itself.
See MODULES_GUIDE.txt for details.
"""

# 1. Description. "id" must be unique and contain no spaces. It is stored in config.json.
MODULE = {
    "id": "my_module",
    "name": {"ru": "My module", "en": "My module"},
    "description": {"ru": "What the module does.", "en": "What the module does."},
    "version": "1.0.0",
    "author": "you",
}


# 2. Entry point. numbinder calls it in a separate thread when a button with this module is pressed.
#    ctx: helpers provided by numbinder
#        ctx.osd("text")        show a message on screen
#        ctx.log("text")        write a line to this run's log (crashlogs)
#        ctx.settings()         the module's own settings dictionary (saved in config.json)
#        ctx.save_settings()    save config.json after changing ctx.settings()
#    cfg: the button's own settings (Type, Path, ProcessName, and so on)
def run(ctx, cfg):
    ctx.log("my_module started")
    ctx.osd("Hello from the module!")
