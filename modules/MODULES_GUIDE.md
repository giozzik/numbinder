# Модули numbinder / Modules guide

Модуль — это один Python-файл (`.py`) в папке `C:\numbinder\modules\`. numbinder находит его при запуске и добавляет в список «Тип» кнопок (Type / Тип). Каждый модуль — отдельный «тип действия».

A module is a single `.py` file in `C:\numbinder\modules\`. numbinder loads it on startup and adds it to the button «Type» list.

> ⚠ Модули выполняются с правами вашей учётной записи. Ставьте только код, которому доверяете. / Modules run with your account's rights. Install only code you trust.

---

## 1. Установка модуля / Installing a module

**Из приложения / From the app:** Настройки → Модули → **Установить модуль…** (Settings → Modules → Install module…). При первой установке появится окно с предупреждением, его нужно принять.
**Вручную / Manually:** положите `.py` в `C:\numbinder\modules\` (кнопка «Открыть папку» / "Open folder") и перезапустите numbinder.

После установки откройте настройки кнопки и выберите модуль в поле «Тип» (он начинается с 🧩).

## 2. Создание модуля / Writing a module

1. Скопируйте `modules\_template.py` и переименуйте, например `my_module.py`.
2. Заполните `MODULE` (см. ниже).
3. Напишите функцию `run(ctx, cfg)`.
4. Положите файл в `C:\numbinder\modules\` и перезапустите numbinder.

### Обязательная структура / Required structure

```python
MODULE = {
    "id": "my_module",                                   # уникальный, без пробелов
    "name": {"ru": "Мой модуль", "en": "My module"},     # название в списке
    "description": {"ru": "...", "en": "..."},           # необязательно
    "version": "1.0.0",                                  # необязательно
    "author": "you",                                     # необязательно
}

def run(ctx, cfg):
    ...
```

Если в файле нет `MODULE` с `id` или нет функции `run`, модуль пропускается и ошибка пишется в лог (`C:\numbinder\crashlogs\`).

### Помощники `ctx` / Helpers

| Что / What | Как / How |
|---|---|
| Показать сообщение на экране / Show a message | `ctx.osd("текст")` |
| Записать в лог / Write to log | `ctx.log("текст")` |
| Свои настройки / Own settings | `ctx.settings()` → словарь, сохраняется в `config.json` |
| Сохранить настройки / Save settings | `ctx.save_settings()` |

`cfg` — настройки кнопки: `cfg.get("Type")`, `cfg.get("Path")`, `cfg.get("ProcessName")` и т. д.

Ошибка внутри `run` не ломает приложение: она пишется в лог текущего запуска и показывается сообщением.

### Полезные библиотеки / Useful libraries

Модуль может импортировать любые пакеты, установленные через pip (например, `pyperclip`, `requests`). Для numbinder уже установлены: `pyperclip`, `psutil`, `pycaw`, `pystray`, `Pillow`, `comtypes`. Для остальных сначала выполните `python -m pip install имя_пакета`.

## 3. Пример / Example

`modules\layout_fixer.py` — встроенный модуль исправления раскладки. Читайте его как образец.

## 4. Советы / Tips

- Не блокируйте `run` надолго: он выполняется в отдельном потоке, но длинные задачи лучше делить.
- Для горячих клавиш и действий с окнами пользуйтесь Windows API (`ctypes`) или `pyperclip`/`psutil`, как в примерах.
- Чтобы изменения в модуле подхватились, перезапустите numbinder.
- Имена файлов с `_` в начале (например, `_template.py`) numbinder не загружает.
