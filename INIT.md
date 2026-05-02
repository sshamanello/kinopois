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
