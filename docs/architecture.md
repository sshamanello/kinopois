# Architecture

`kinopois` is split into three stages plus a publish queue:

1. `download/` — fetches raw movie data and posters from Kinopoisk API
2. `processing/` — cleans rows, builds poster collages or framed assets, syncs to local cache DB
3. `publishing/` — builds Pinterest-ready pin rows, writes them to Postgres, and drives the autopilot

## Data flow

```text
Kinopoisk.dev API
  → data/cache/movies.csv          raw API data (kp_id, title, rating_kp, poster_url…)
  → data/cache/movies_clean.csv    cleaned, primary_genre added
  → data/cache/pins.csv            pin rows with SEO titles/descriptions
  → Postgres kinopois_pins          publish queue (single source of truth)
  → n8n / autopilot / Pinterest API
```

The collage pipeline is independent from the pin-export pipeline.

## Module layout

```text
kinopois/
  cli.py                 Click CLI — all commands
  config.py              Env-backed config singleton (no from_env duplication)
  interactive.py         Sync questionary-based TUI menu
  logging_setup.py       Python logging with rotating file handler
  utils.py              CSV/parsing helpers

  download/
    scraper.py           Kinopoisk API client, poster download with retry

  processing/
    processor.py         Movie data cleaning, genre grouping
    collage.py           2x2 poster collage builder
    marker.py            Watermark/overlay on poster images
    frame.py             Framed poster renderer for Pinterest

  publishing/
    movie_pins.py         Build/export individual pin rows, SEO generators
    collage_export.py     Export collages to CSV (Pinterest/simple/summary)
    pipeline_steps.py     Composable pipeline: download → process → upload → publish
    postgres_queue.py     Postgres publish queue (kinopois_pins table)
    pinterest.py          Direct Pinterest API publish client
    autopilot.py          Autonomous scheduler (harvest + timed publish slots)
    db.py                 SQLite cache (movies_raw, movies_clean, collages)
    eventlog.py           JSONL structured event logger
```

## Config

All settings come from environment variables, read via dataclass defaults.
No `from_env()` duplication — adding a new field means adding one line in `Config`.

## Logging

- `console.print()` — user-facing Rich output (CLI only)
- `log_event()` — structured JSONL events (data/logs/events.log)
- `logger.info/debug/error` — Python logging with rotation (data/logs/kinopois.log)