# kinopois

`kinopois` is a Python CLI for downloading Kinopoisk posters, cleaning movie metadata, and exporting Pinterest-ready rows for automated publishing.

## Project layout

```text
kinopois/
  download/          Kinopoisk API client and poster download
  processing/        CSV cleaning, collages, framing, watermarking
  publishing/        Pin row building, Postgres queue, autopilot
  cli.py             Click CLI entrypoint
  config.py          Env-backed configuration singleton
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

## Common commands

```bash
kinopois download --limit 200                 # Download posters
kinopois process                               # Clean movie data
kinopois export-movie-pins                    # Export pins to CSV
kinopois pins --limit 200 --sync-queue        # Full pin pipeline + queue sync
kinopois run-base-pipeline --limit 200        # Production pipeline -> Postgres
kinopois queue-ready --limit 5               # Show ready jobs (JSON)
kinopois db-stats                              # Show queue counts
kinopois autopilot-once                        # One autopilot tick
kinopois autopilot                             # Daemon mode
```

## Configuration

Copy `.env.example` to `.env` and set at least:

```env
KINOPOISK_API_KEY=...
PINTEREST_ACCESS_TOKEN=...
PINTEREST_BOARD_ID=...
POSTERS_BASE_URL=https://your-domain.example/posters
FRAMED_POSTERS_BASE_URL=https://your-domain.example/posters_framed
PUBLISH_IMAGES_BASE_URL=https://your-domain.example/pins/ready
PUBLISH_REMOTE_SYNC_ENABLED=0
```

The publish queue lives in Postgres (`kinopois_pins`) and is read by n8n.

## Logging

- `data/logs/kinopois.log` — Python logging with rotation (INFO+)
- `data/logs/events.log` — Structured JSONL events (audit trail)
- Console output via Rich (user-facing only)

## Documentation

- [Architecture](docs/architecture.md)
- [Usage](docs/usage.md)
- [Deployment](docs/deployment.md)
- [Data contracts](docs/data-contracts.md)
- [Project notes](docs/INIT.md)
- [Historical context](docs/CLAUDE.md)