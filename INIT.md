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
