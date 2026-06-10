# INIT.md — Kinopois quick context

> Last updated: 2026-06-10

## 2026-06-10 — Full refactoring

### Config simplification
- Removed `Config.from_env()` — the dataclass defaults already read env vars via `os.getenv`.
- Added helper functions `_env_bool`, `_env_int`, `_env_str`, `_env_path` for readability.
- Added `log_dir` and `log_level` config fields for the new logging module.

### db.py cleanup
- Removed dead `publish_jobs` table from SQLite init.
- Removed Postgres delegation stubs (`sync_publish_job_rows`, `get_ready_jobs`, `mark_posted`, `mark_failed`, `claim_ready_jobs`, `db_counts`, `sync_pins_csv`).
- All Postgres queue operations now go directly through `postgres_queue.py`.
- Removed `db_path` parameter from remaining SQLite functions.

### postgres_queue.py cleanup
- Removed `db_path` parameter from all function signatures.
- Added `_db_initialized` flag so `init_db()` CREATE TABLE runs only once per process.
- Organized code into sections: connection helpers, row sync, queue queries.

### CLI consolidation
- Removed 4 redundant commands: `run`, `run-prod`, `backfill-assets`, `queue-sync`.
- Remaining commands: `download`, `process`, `collage`, `mark`, `export`, `export-movie-pins`, `pins`, `run-base-pipeline`, `clean`, `info`, `menu`, `db-init`, `db-sync-all`, `db-stats`, `queue-ready`, `queue-posted`, `queue-failed`, `autopilot`, `autopilot-once`.

### export.py split
- `export.py` → `movie_pins.py` (build/export pin rows, SEO generators, genre map) + `collage_export.py` (collage CSV export, title templates, summary).
- All imports updated across cli.py, interactive.py, pipeline_steps.py.

### interactive.py simplification
- Converted all `ask_async()` → `ask()` (sync).
- Removed `async/await`, `import asyncio`, `asyncio.run()`.
- Removed unused `click` and `Optional` imports.

### Logging module
- Added `kinopois/logging_setup.py` with `get_logger(name)`.
- Rotating file handler at `data/logs/kinopois.log` (10MB, 5 backups, INFO+).
- Console handler (WARNING+) for production visibility.
- Added `logger` to key pipeline modules: scraper, processor, collage, pipeline_steps, postgres_queue, autopilot, movie_pins.

## Base architecture (unchanged)

```
kinopois/
  download/          Kinopoisk API client and poster download
  processing/        CSV cleaning, collages, framing, watermarking
  publishing/         Pin row building, Postgres queue, Pinterest API, autopilot
  cli.py              Click CLI — all commands
  config.py           Env-backed configuration singleton
  interactive.py      Sync questionary-based TUI menu
  logging_setup.py    Python logging with file rotation
  utils.py            Shared CSV and parsing helpers
```

## Data flow

```
Kinopoisk.dev API
  → data/cache/movies.csv (raw API snapshot)
  → SQLite movies_raw / movies_clean / collages (local cache)
  → Postgres kinopois_pins (publish queue)
  → n8n / autopilot / Pinterest API
```

## Key invariant

- Postgres `kinopois_pins` is the single source of truth for publish state.
- SQLite is a local cache for download/processing data only.

## Base launch on server

```bash
# One-shot
kinopois run-base-pipeline --limit 200

# Daemon
kinopois autopilot

# Manual pin pipeline
kinopois pins --limit 200 --sync-queue

# Queue inspection
kinopois queue-ready --limit 5
kinopois db-stats
```