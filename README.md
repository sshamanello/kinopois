# kinopois

`kinopois` is a Python CLI for downloading Kinopoisk posters, cleaning movie metadata, and exporting Pinterest-ready rows for automated publishing.

**Everything runs locally** — no remote servers needed. Pinterest API receives base64-encoded image data from local files.

## Project layout

```text
kinopois/
  download/          Kinopoisk API client and poster download
  processing/        CSV cleaning, collages, framing, watermarking
  publishing/        Pin row building, Postgres queue, autopilot
  cli.py             Click CLI entrypoint
  config.py          Env-backed configuration singleton (all local paths)
  interactive.py     Sync questionary-based TUI menu
  logging_setup.py   Python logging with file rotation
  utils.py           Shared CSV and parsing helpers
docs/                Full project documentation
```

## Main flow

1. `kinopois download` pulls raw movie data, writes posters, and syncs rows into the local cache DB
2. `kinopois process` cleans the dataset and syncs cleaned rows into the local cache DB
3. `kinopois run-base-pipeline` builds publishable rows and syncs them into the Postgres publish queue (`kinopois_pins`)
4. `kinopois export-movie-pins` is still available as an explicit CSV export if you need a snapshot

The collage pipeline is separate and writes `data/collages/` plus `data/cache/collages.csv`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

On the server (192.168.10.122), use `PYTHONPATH` instead:

```bash
cd /home/nick/kinopois
PYTHONPATH=/home/nick/kinopois python3 -m kinopois --help
```

## Common commands

```bash
# Full pipeline (daily cron at 21:00 MSK)
PYTHONPATH=/home/nick/kinopois python3 -m kinopois run-base-pipeline --limit 200

# Download only
PYTHONPATH=/home/nick/kinopois python3 -m kinopois download --limit 200

# Process only
PYTHONPATH=/home/nick/kinopois python3 -m kinopois process

# Export pins CSV
PYTHONPATH=/home/nick/kinopois python3 -m kinopois export-movie-pins

# Full pin pipeline + queue sync
PYTHONPATH=/home/nick/kinopois python3 -m kinopois pins --limit 200 --sync-queue

# Queue inspection
PYTHONPATH=/home/nick/kinopois python3 -m kinopois queue-ready --limit 5
PYTHONPATH=/home/nick/kinopois python3 -m kinopois db-stats

# Autopilot
PYTHONPATH=/home/nick/kinopois python3 -m kinopois autopilot-once
PYTHONPATH=/home/nick/kinopois python3 -m kinopois autopilot
```

## Configuration

Copy `.env.example` to `.env` and set at least:

```env
KINOPOISK_API_KEY=...
PINTEREST_ACCESS_TOKEN=...
PINTEREST_BOARD_ID=...
```

All image paths are **local** by default:

```env
POSTERS_BASE_URL=data/posters
FRAMED_POSTERS_BASE_URL=data/posters_framed
PUBLISH_IMAGES_BASE_URL=data/publish/ready
```

Pinterest publishing uses base64 upload from local files — no public URL or remote server needed.

The publish queue lives in Postgres (`kinopois_pins`) and is read by n8n.

## Cron (daily at 21:00 MSK)

```bash
CRON_TZ=Europe/Moscow
0 21 * * * cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois FRAMED_FORCE_REGENERATE=0 FRAMED_REFRESH_SOURCE=0 python3 -m kinopois run-base-pipeline --limit 200 >> /home/nick/kinopois/data/logs/cron.log 2>&1
```

## Logging

- `data/logs/kinopois.log` — Python logging with rotation (INFO+)
- `data/logs/events.log` — Structured JSONL events (audit trail)
- `data/logs/cron.log` — Cron output
- Console output via Rich (user-facing only)

## Documentation

- [Architecture](docs/architecture.md)
- [Usage](docs/usage.md)
- [Deployment](docs/deployment.md)
- [Data contracts](docs/data-contracts.md)
- [Project notes](docs/INIT.md)
- [Historical context](docs/CLAUDE.md)