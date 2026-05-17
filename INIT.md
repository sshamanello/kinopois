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

## Изменения 2026-05-11 (n8n status reconcile hardening)

- Подтвержден критичный источник рассинхрона статусов: в одном workflow-файле n8n
  нода `Update row - failed` матчила строку по `status`, а не по `id`.
- Добавлена функция `normalize_sheet_statuses()` в `kinopois/sheets.py`.
- Добавлена CLI-команда:
  - `kinopois reconcile-sheet-statuses`
  - исправляет пустые/невалидные статусы в Google Sheets:
    - `posted_at` заполнен -> `status=posted`
    - `posted_at` пуст и status пуст/битый -> `status=pending`
- Добавлен скрипт `scripts/reconcile_sheet_statuses.py` с такой же логикой
  для одноразового ручного запуска.
- README дополнен новой командой обслуживания таблицы.

## Изменения 2026-05-11 (download hardening for transient API 403)

- Усилена загрузка Kinopoisk в `kinopois/scraper.py`:
  - добавлен retry (до 3 попыток) в `fetch_movies` с коротким backoff.
- Добавлена защита от потери кэша:
  - если `download` запущен в режиме перезаписи и API вернул 0 фильмов,
    `movies.csv` автоматически восстанавливается из предыдущего снапшота.
- Это защищает прод-контур от ситуации «временный 403 обнулил очередь».

## Изменения 2026-05-11 (switch off sshamanello + auto-cleanup on VDS)

- Убраны дефолтные URL `sshamanello.ru` из `config.py`:
  - `BASE_IMAGE_URL`, `POSTERS_BASE_URL`, `FRAMED_POSTERS_BASE_URL`
  - теперь дефолты указывают на `http://87.120.219.4/...`.
- Добавлена автоочистка publish-директории:
  - `PUBLISH_IMAGES_CLEANUP_ENABLED` (default `1`)
  - `PUBLISH_IMAGES_RETENTION_DAYS` (default `21`)
  - новый шаг `step_cleanup_publish_dir()` в `pipeline_steps.py`
  - вызывается автоматически в `run_daily_prepare`.
- `.env.example` и `README.md` обновлены под схему `87.120.219.4` + cleanup.

## Изменения 2026-05-11 (remote sync to 87.120.219.4)

- Добавлена опциональная удалённая выгрузка publish-изображений:
  - `PUBLISH_REMOTE_SYNC_ENABLED`
  - `PUBLISH_REMOTE_HOST`
  - `PUBLISH_REMOTE_USER`
  - `PUBLISH_REMOTE_DIR`
- При включении (`PUBLISH_REMOTE_SYNC_ENABLED=1`) `step_upload_to_server()`:
  - копирует файл локально,
  - затем отправляет `scp` на удалённый хост (`87.120.219.4`).
- В `step_cleanup_publish_dir()` добавлена удалённая очистка:
  - `ssh find ... -mtime +N -delete` по `PUBLISH_IMAGES_RETENTION_DAYS`.

## Изменения 2026-05-11 (hard backfill for images + sheets)

- `step_upload_to_server()` усилен fallback-логикой:
  - если локальный source-постер не найден, выполняется докачка по `poster_url`,
    затем файл отправляется в publish-контур.
- Добавлен selective sync upload-полей в Sheets:
  - `sync_upload_fields_to_sheets()` обновляет по `id` только:
    `image_url`, `public_image_url`, `remote_image_path`,
    `vds_upload_status`, `uploaded_at`, `publish_status`, `error_reason`.
- Добавлена CLI-команда:
  - `kinopois backfill-assets --limit 200`
  - выполняет prepare + selective upload-fields sync в таблицу.

## Изменения 2026-05-11 (stable auto-copy after processing)

- Исправлена нестабильность remote-copy в `step_upload_to_server()`:
  - добавлен `BatchMode=yes` для `scp`, чтобы процесс не зависал на запросе пароля;
  - добавлен `ConnectTimeout` и общий `timeout` выполнения команды;
  - ошибки remote-copy теперь возвращаются как явные `upload_failed` причины в `error_reason`.
- Добавлены новые env-настройки:
  - `PUBLISH_REMOTE_CONNECT_TIMEOUT_SEC` (default `8`)
  - `PUBLISH_REMOTE_CMD_TIMEOUT_SEC` (default `25`)
- Усилен remote cleanup (`ssh find ... -delete`):
  - та же fail-fast SSH-конфигурация (`BatchMode`, `ConnectTimeout`, `timeout`);
  - безопасная обработка исключений без падения daily-пайплайна.

## Изменения 2026-05-12 (poiskkino TLS fallback via --resolve)

- Для `download` добавлен fallback на `curl --resolve` при сетевых/TLS ошибках
  к `api.poiskkino.dev`:
  - сначала идёт обычный `requests.get`,
  - если он падает, пробуются IP из `KINOPOISK_RESOLVE_IPS`.
- Добавлены env-параметры:
  - `KINOPOISK_API_URL` (default `https://api.poiskkino.dev/v1.4/movie`)
  - `KINOPOISK_RESOLVE_IPS` (comma-separated список IP для fallback).

## Изменения 2026-05-12 (strict new-only download, no duplicates)

- Команда `kinopois download` переведена в append-only режим по умолчанию:
  - новые записи дописываются в `movies.csv`,
  - существующие `kp_id` всегда пропускаются.
- Добавлен явный флаг `--replace` для ручного полного пересоздания `movies.csv`
  (по умолчанию не используется в проде).
- Проверка на сервере двумя подряд запусками `download --limit 10`:
  - после 1-го запуска: `20 total / 20 unique / 0 dup`,
  - после 2-го запуска: `30 total / 30 unique / 0 dup`.

## Изменения 2026-05-17 (dockerized prod runtime)

- `docker-compose.yml` разделён на 2 сервиса:
  - `kinopois-prepare` — one-shot подготовка (`run-pins --sync-sheets`);
  - `kinopois-autopilot` — постоянный daemon (`kinopois autopilot`, `restart: always`).
- Добавлен persistent mount для логов контейнера:
  - `./logs:/app/logs`.
- Обновлены deploy-скрипты:
  - `deploy/cron-setup.sh` теперь использует `kinopois-prepare`;
  - `deploy/server-setup.sh` дополнен шагом `docker compose up -d kinopois-autopilot`.
- README обновлён под новый Docker-flow и команды анализа логов.

## Изменения 2026-05-17 (remove hard 10-per-page clamp)

- Убран жёсткий лимит `limit=10` для `api.poiskkino.dev` в `scraper.py`.
- Теперь `download` использует фактический `page_size` из конфигурации и может
  набирать дневной лимит до `AUTOPILOT_DOWNLOAD_LIMIT_PER_DAY=200`.
- Логика "только новые" сохранена:
  - append-only запись в `movies.csv`;
  - пропуск уже существующих `kp_id`;
  - дублей по `kp_id` в выгрузке не добавляется.

## Изменения 2026-05-17 (network hardening for poster downloads)

- Усилено скачивание постеров в `scraper.py`:
  - до 3 попыток на один URL с коротким backoff;
  - fallback URL: сначала `poster.url`, затем `poster.previewUrl`, если основной не скачался.
- Для Docker-сервисов `kinopois-prepare` и `kinopois-autopilot` добавлены
  явные DNS-серверы (`1.1.1.1`, `8.8.8.8`) в `docker-compose.yml` для
  снижения ошибок резолвинга `avatars.mds.yandex.net`.

## Изменения 2026-05-17 (anti-dup + faster upload pass)

- Добавлена файловая блокировка `movies.csv.lock` в `download_and_save()`:
  - параллельные запуски больше не пишут в `movies.csv` одновременно;
  - снижает риск дублей при одновременном `autopilot` и ручном запуске.
- `step_upload_to_server()` переведён в инкрементальный режим:
  - строки с `vds_upload_status=uploaded` и существующим файлом в
    `data/publish/ready` пропускаются;
  - не гоняет каждый раз весь массив загруженных изображений заново;
  - добавлено поле статистики `skipped`.

## Изменения 2026-05-17 (detailed structured logging)

- Добавлен модуль `kinopois/eventlog.py` с JSONL-логом событий.
- Файл логов: `data/logs/events.log`.
- Логируются ключевые этапы:
  - `run_daily_prepare_*`, `step_download_*`, `step_process_*`,
    `step_export_*`, `step_upload_*`, `step_cleanup_*`, `step_queue_sync_*`;
  - `autopilot_*` события тиков, harvest и публикационных слотов;
  - сетевые ошибки `fetch_movies_failed`, `poster_download_failed`,
    а также fallback `fetch_movies_fallback_resolve`.
