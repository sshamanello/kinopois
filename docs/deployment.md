# Deployment

## Server: 192.168.10.122

- User: `nick`
- Project dir: `/home/nick/kinopois/`
- Python: system `python3` with `PYTHONPATH=/home/nick/kinopois`
- No Docker needed — runs directly via Python
- Postgres: local on `127.0.0.1:5432`, DB `pinterest`, user `pinterest`

## Cron (daily pipeline)

```bash
CRON_TZ=Europe/Moscow
0 21 * * * cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois FRAMED_FORCE_REGENERATE=0 FRAMED_REFRESH_SOURCE=0 python3 -m kinopois run-base-pipeline --limit 200 >> /home/nick/kinopois/data/logs/cron.log 2>&1
```

- Runs at 21:00 MSK daily
- `FRAMED_FORCE_REGENERATE=0` — reuses existing framed posters (no re-download)
- `FRAMED_REFRESH_SOURCE=0` — skips re-downloading clean poster sources
- Log output goes to `data/logs/cron.log`

## Environment (.env)

Located at `/home/nick/kinopois/.env`. All paths are local — no remote server references.

Key variables:
```
KINOPOISK_API_KEY=...
QUEUE_DB_HOST=127.0.0.1
QUEUE_DB_PORT=5432
QUEUE_DB_NAME=pinterest
QUEUE_DB_USER=pinterest
QUEUE_DB_PASSWORD=pinterest_pass_2026
PUBLISH_IMAGES_BASE_URL=data/publish/ready
FRAMED_FORCE_REGENERATE=0
FRAMED_REFRESH_SOURCE=1
```

## Docker (optional)

```bash
docker compose build
docker compose run --rm kinopois-prepare run-base-pipeline --limit 200
docker compose up -d kinopois-autopilot
```

Docker is not required for normal operation — the cron job runs Python directly.

## Logs

```bash
# Application logs (rotated, 10MB x 5)
tail -f data/logs/kinopois.log

# Structured audit events (JSONL)
tail -f data/logs/events.log

# Cron output
tail -f data/logs/cron.log
```

## Image storage

All images stored locally on disk. Pinterest API receives base64-encoded image data directly from local files — no public web server or remote host needed.

```
data/posters/          — original downloaded posters (4234 files)
data/posters_framed/   — framed posters for Pinterest (3610 files)
data/posters_clean/    — clean posters without watermarks (3408 files)
data/publish/ready/    — copies ready for publishing (3439 files)
data/collages/          — 2x2 collage images
data/cache/             — CSV snapshots (movies.csv, movies_clean.csv, pins.csv)
```