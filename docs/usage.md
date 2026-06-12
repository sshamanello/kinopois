# Usage

All commands require `PYTHONPATH` set to the project root.

## Quick start

```bash
cd /home/nick/kinopois
export PYTHONPATH=/home/nick/kinopois
```

## Download

```bash
python3 -m kinopois download --limit 200
```

## Processing

```bash
python3 -m kinopois process
python3 -m kinopois collage --watermark "@YourBot" --max-per-genre 2
```

## Publishing

```bash
# Full pipeline: download → process → build pins → upload → sync queue → cleanup
python3 -m kinopois run-base-pipeline --limit 200

# Export pins CSV only (no DB sync)
python3 -m kinopois export-movie-pins

# Manual pin pipeline
python3 -m kinopois pins --limit 200 --sync-queue
```

`run-base-pipeline` writes publishable rows directly into `kinopois_pins`; it no longer depends on `pins.csv` as an intermediate queue handoff.

## Queue management

```bash
python3 -m kinopois db-init                    # Initialize Postgres schema
python3 -m kinopois db-sync-all                # Sync all CSVs → SQLite + Postgres
python3 -m kinopois db-stats                    # Show queue counts
python3 -m kinopois queue-ready --limit 5      # Show ready jobs as JSON
python3 -m kinopois queue-posted --job-id 1 --pin-id abc123
python3 -m kinopois queue-failed --job-id 1 --error "API error"
```

## Autopilot

```bash
python3 -m kinopois autopilot-once             # One tick (harvest + post slots)
python3 -m kinopois autopilot                  # Daemon mode (runs forever)
```

## Interactive menu

```bash
python3 -m kinopois                            # Launch TUI menu
python3 -m kinopois menu                       # Same as above
```

## Cron (daily, 21:00 MSK)

```bash
CRON_TZ=Europe/Moscow
0 21 * * * cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois FRAMED_FORCE_REGENERATE=0 FRAMED_REFRESH_SOURCE=0 python3 -m kinopois run-base-pipeline --limit 200 >> /home/nick/kinopois/data/logs/cron.log 2>&1
```

## Environment variables

Key variables (see `.env.example` for full list):

```
KINOPOISK_API_KEY=           # required for download
POSTERS_BASE_URL=            # local path (default: data/posters)
FRAMED_POSTERS_BASE_URL=     # local path (default: data/posters_framed)
BOT_URL=                     # Telegram bot URL used in pin descriptions
PUBLISH_IMAGES_BASE_URL=     # local path (default: data/publish/ready)
FRAMED_FORCE_REGENERATE=0   # reuse existing framed posters
FRAMED_REFRESH_SOURCE=0     # skip re-downloading clean poster sources
```

All image paths are local — Pinterest uses base64 upload from local files, no public URL needed.