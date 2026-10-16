# Qiqi

Локальный каталог промптов для Qwen Image.

## Установка

```bash
uv sync
```

## Запуск

```bash
uv run qiqi
# или
uv run python -m qiqi
```

По умолчанию: http://127.0.0.1:8765

## Конфиг

Файл `qiqi.yaml` рядом со скриптом (или в CWD). Если нет — создаётся с дефолтами.

```yaml
db_path: prompts.sqlite
previews_dir: previews
exports_dir: exports
server:
  host: 127.0.0.1
  port: 8765
qwen:
  default_cfg: 2.5
  cfg_green: [2.0, 3.0]
  cfg_orange: [1.5, 4.0]
```

Пути внутри конфига — относительно самого `qiqi.yaml`.

## Что уже работает

- Группы (создание, переименование, удаление).
- Промпты внутри групп: title, positive, negative, cfg, comment, rating 0–12, favorite.
- Подсветка cfg: зелёная / оранжевая / красная зона.
- Всё хранится в `prompts.sqlite`.

## Что дальше (по шагам)

- Шаг 2: фильтры и сортировки в UI.
- Шаг 3: `jobs` — «Заказать превью» / «Заказать фуллсайз» для промпта и группы.
- Шаг 4: `files` — отображение сгенерированных превью.
- Шаг 5: экспорт в `.py` и `.json` для билдера.
- Шаг 6: внешний сервис-воркер для Qwen Image.