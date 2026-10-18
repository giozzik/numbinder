"""
ШАБЛОН МОДУЛЯ numbinder.
Скопируйте этот файл, переименуйте (например, my_module.py) и поменяйте значения ниже.
Файлы, имя которых начинается с "_", numbinder не загружает — поэтому шаблон сам не запускается.
Подробнее: MODULES_GUIDE.txt
"""

# 1. Описание. "id" должен быть уникальным и без пробелов. Именно он попадает в config.json.
MODULE = {
    "id": "my_module",
    "name": {"ru": "Мой модуль", "en": "My module"},
    "description": {"ru": "Что делает модуль.", "en": "What the module does."},
    "version": "1.0.0",
    "author": "you",
}


# 2. Точка входа. numbinder вызывает её в отдельном потоке, когда нажата кнопка с этим модулем.
#    ctx — помощники:
#        ctx.osd("текст")          показать сообщение на экране
#        ctx.log("текст")          записать в лог текущего запуска (crashlogs)
#        ctx.settings()            словарь настроек модуля (хранится в config.json)
#        ctx.save_settings()       сохранить config.json после изменения ctx.settings()
#    cfg — настройки самой кнопки (Type, Path, ProcessName и т. д.).
def run(ctx, cfg):
    ctx.log("my_module started")
    ctx.osd("Привет от модуля!")
