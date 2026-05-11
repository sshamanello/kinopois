# INIT.md — Быстрый контекст kinopois

> Последнее обновление: 2026-05-02

## Правило ведения INIT.md

- При любом изменении проекта обновлять `INIT.md` в том же коммите.
- Кратко фиксировать что изменено и зачем.

## Изменения 2026-05-02

- Добавлен автономный scheduler для server-run без ручного участия:
  - новый модуль: `kinopois/autopilot.py`
  - новый CLI:
    - `kinopois autopilot` — daemon-режим (крутится весь день)
    - `kinopois autopilot-once` — один цикл для проверки
- Целевая логика автопилота:
  - раз в день делает harvest (download -> process -> export pins),
  - соблюдает лимит Kinopoisk API через `AUTOPILOT_DOWNLOAD_LIMIT_PER_DAY` (по умолчанию `200`),
  - запускает до `AUTOPILOT_POSTS_PER_DAY` слот-попыток публикации (по умолчанию `3`) в часы `AUTOPILOT_SLOT_HOURS` c jitter `AUTOPILOT_SLOT_JITTER_MIN`.
- Добавлен state-файл автопилота:
  - `data/cache/autopilot_state.json`
  - хранит день, слоты, факт harvest и результаты слот-публикаций.
- Добавлен внешний hook для публикации:
  - `AUTOPILOT_PUBLISH_COMMAND`
  - команда получает JSON job через `stdin`
  - при `exit code != 0` job отмечается failed, при успехе — posted.
- Добавлены опциональные Telegram-уведомления:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - используются для startup/error/daily-status.
- Добавлен накопительный режим загрузки постеров:
  - `KinopoiskScraper.download_and_save(..., append_mode=True)`
  - не перезаписывает `movies.csv`, а добавляет только новые `kp_id`
  - это позволяет накопить тысячи постеров в первые недели и публиковать из большого пула месяцами.
- Обновлены:
  - `.env.example` (новые `AUTOPILOT_*` и Telegram env)
  - `README.md` (автономный режим и новые команды).

## Базовый запуск на сервере

1. Заполнить `.env` (API ключ, Sheets, при необходимости `AUTOPILOT_PUBLISH_COMMAND`, Telegram).
2. Прогон проверки:
   - `kinopois autopilot-once`
3. Постоянный запуск:
   - `kinopois autopilot`
   - или через systemd/pm2/supervisord.

## Важно

- Если `AUTOPILOT_PUBLISH_COMMAND` пустой, harvest/queue/sheets будут работать, но слот публикации будет помечаться как skip.
- Для полностью автономной публикации нужен рабочий publish hook (или внешний n8n, который читает очередь/таблицу и постит сам).

## Изменения 2026-05-02 (рамочные креативы)

- В movie-pins пайплайн включены рамочные креативы по умолчанию:
  - новый модуль: `kinopois/frame.py`
  - экспорт теперь для каждого `kp_id` генерирует framed-изображение в `data/posters_framed/{kp_id}.jpg`
  - `pins.csv:image_url` указывает на `FRAMED_POSTERS_BASE_URL/{kp_id}.jpg` при `USE_FRAMED_POSTERS=1`.
- Рамка делается уникализированной (детерминированно от `kp_id`):
  - разные акцентные цвета/полосы/зерно,
  - без watermark/`@bot` на изображении.
- Добавлены env-поля:
  - `FRAMED_POSTERS_DIR`
  - `FRAMED_POSTERS_BASE_URL`
  - `USE_FRAMED_POSTERS`.

## Изменения 2026-05-02 (убран старый @bot из framed source)

- Найдена причина появления `@bot` в рамочных креативах:
  - часть локальных `data/posters/*.jpg` уже была ранее промаркирована.
- Исправление:
  - для framed-рендера добавлен refresh чистого источника из `poster_url` перед генерацией рамки.
  - если загрузка оригинала не удалась, используется fallback на локальный файл.
- Добавлены env-параметры:
  - `FRAMED_SOURCE_POSTERS_DIR` (кеш чистых исходников)
  - `FRAMED_REFRESH_SOURCE` (`1` по умолчанию).

## Изменения 2026-05-02 (принудительная перегенерация framed)

- Добавлен флаг `FRAMED_FORCE_REGENERATE=1` по умолчанию.
- Экспорт movie-pins теперь перерисовывает `data/posters_framed/{kp_id}.jpg` при каждом экспорте, если флаг включен.
- Это устраняет проблему старого кэша framed-файлов, где мог оставаться исторический `@Бот`.

## Изменения 2026-05-02 (CLI test run + source watermark fix)

- Исправлен источник постера в scraper:
  - вместо `poster_preview_url` теперь используется `poster_url` (full size),
  - причина: preview-варианты чаще несут watermark/хуже по качеству.
- Исправлен баг `--data-dir`:
  - CLI теперь создаёт все целевые каталоги (`posters`, `posters_clean`, `posters_framed`, `collages`, `cache`) до запуска команд.
- Прогнан изолированный end-to-end тест через CLI на 3 свежих постерах:
  - `python3 -m kinopois --data-dir data/test_run download --limit 3`
  - `python3 -m kinopois --data-dir data/test_run process`
  - `python3 -m kinopois --data-dir data/test_run export-movie-pins --limit 3`
  - framed output: `data/test_run/posters_framed/{kp_id}.jpg`.

## Изменения 2026-05-02 (Python-only post без n8n)

- Добавлен прямой постинг в Pinterest API из Python:
  - новый модуль: `kinopois/pinterest.py`
  - endpoint: `POST https://api.pinterest.com/v5/pins`
  - берёт `PINTEREST_ACCESS_TOKEN` из env.
- Autopilot теперь публикует без n8n по умолчанию:
  - если `AUTOPILOT_PUBLISH_COMMAND` пустой, используется прямой `publish_pin(job)`.
  - если `AUTOPILOT_PUBLISH_COMMAND` задан, он остаётся override-режимом.
- Для board выбора:
  - сначала `job.board_id` из `pins.csv`/queue,
  - fallback: `PINTEREST_BOARD_ID`.

Итог: стабильный цикл `скачать -> обработать -> сохранить -> постить` полностью внутри kinopois.

## Изменения 2026-05-02 (retry next poster inside slot)

- Обновлена логика публикационного слота в `autopilot`:
  - если текущий `ready` job падает, слот не заканчивается,
  - автопилот сразу пробует следующий `ready` job,
  - слот считается успешным при первом успешном посте.
- Добавлен env-параметр:
  - `AUTOPILOT_PUBLISH_ATTEMPTS_PER_SLOT` (default `5`) — сколько `ready` задач можно перебрать в одном слоте до остановки.
- Если все попытки в слоте упали, слот помечается как `failed_all`.

## Изменения 2026-05-02 (SEO titles for Pinterest)

- В `export_movie_pins_csv` заголовок `title` больше не равен сырому названию фильма.
- Добавлен SEO-генератор title для Pinterest:
  - шаблоны с интентом "что посмотреть",
  - включение жанра / года / рейтинга,
  - ограничение длины до 100 символов.
- `original_title` и описание остаются как раньше; меняется только поле `title` в `pins.csv`.

## Изменения 2026-05-02 (SEO titles v2 — max reach)

- Усилен генератор Pinterest title в `export.py`:
  - добавлены high-intent шаблоны (`что посмотреть`, `фильм на вечер`, `топ находка`, `сохраните в подборку`),
  - добавлена нормализация жанров в более естественные SEO-формы (`драмы`, `боевики`, `короткометражные фильмы` и т.п.),
  - заголовки ограничены 100 символами.
- Текущая очередь `publish_jobs` для `ready/failed` переписана вручную на v2 SEO titles.

## Изменения 2026-05-02 (SEO descriptions v2 — current + future)

- Усилен генератор `description` в `export.py`:
  - high-intent формулировки (`что посмотреть вечером/сегодня`, `сохраняйте пин`, `подборка`),
  - встроенный CTA в Telegram-бот (`BOT_URL`),
  - включение жанра / года / рейтинга для поисковой релевантности.
- Текущая очередь `publish_jobs` (`ready/failed`) переписана вручную на новый SEO-формат description.

## Изменения 2026-05-11 (modular base architecture skeleton)

- Добавлен модуль шагов `kinopois/pipeline_steps.py` с изолированными этапами:
  - `step_download`
  - `step_process`
  - `step_export`
  - `step_upload_to_server`
  - `step_queue_sync`
  - `step_publish`
- Добавлен агрегирующий сценарий `run_daily_prepare(limit)` для базового контура.
- В `autopilot` ежедневная подготовка переведена на модульный раннер шагов.
- Добавлена CLI-команда:
  - `kinopois run-base-pipeline --limit 200 [--publish N]`
- Расширен CSV/Sheets контракт для интеграции с n8n полями:
  - `public_image_url`, `remote_image_path`, `vds_upload_status`,
  - `uploaded_at`, `publish_status`, `published_at`, `error_reason`.
- Добавлены env-поля для upload слоя:
  - `PUBLISH_IMAGES_DIR`
  - `PUBLISH_IMAGES_BASE_URL`.

## Изменения 2026-05-11 (producer-only mode for n8n split)

- Добавлен флаг `AUTOPILOT_ENABLE_PUBLISH` (default `1`).
- При `AUTOPILOT_ENABLE_PUBLISH=0` `kinopois-autopilot` выполняет только producer-часть:
  - download
  - process
  - export
  - upload images
  - queue/sheets sync
- Публикационные слоты Pinterest в этом режиме пропускаются (n8n публикует отдельно).
