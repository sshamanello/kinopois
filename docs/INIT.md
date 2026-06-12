# INIT.md — Kinopois quick context

> Last updated: 2026-06-12

## 2026-06-12 — Removed remote server dependency (87.120.219.4)

### What changed
- All image URLs now use local paths (e.g. `data/posters_framed/11466997.jpg`) instead of `http://87.120.219.4/...`.
- Pinterest publishing uses base64 upload from local files — no public URL needed.
- Removed remote SCP sync (`_scp_to_remote`, `_remote_target_for_id`) from `pipeline_steps.py`.
- Removed `publish_remote_*` config fields (6 fields): `publish_remote_sync_enabled`, `publish_remote_host`, `publish_remote_user`, `publish_remote_dir`, `publish_remote_connect_timeout_sec`, `publish_remote_cmd_timeout_sec`.
- Removed SSH key mount from `docker-compose.yml`.
- Updated `.env.example` and server `.env` — no remote host references remain.
- `image_url` in Postgres stores local relative paths; `pinterest.py` resolves them to actual files via `_resolve_local_image_path()`.
- Updated 3610 rows in Postgres from `http://87.120.219.4/...` to `data/...` paths.
- Cron on server updated: `PYTHONPATH=/home/nick/kinopois FRAMED_FORCE_REGENERATE=0 FRAMED_REFRESH_SOURCE=0 python3 -m kinopois run-base-pipeline --limit 200` at 21:00 MSKC daily (no Docker, no `--sync-sheets`).

### Config defaults (all local now)

| Field | Default |
|-------|---------|
| `base_image_url` | `data/collages` |
| `posters_base_url` | `data/posters` |
| `framed_posters_base_url` | `data/posters_framed` |
| `publish_images_base_url` | `data/publish/ready` |

### File locations on server (192.168.10.122)

| Directory | Files | Purpose |
|-----------|-------|---------|
| `data/posters/` | 4234 | Original downloaded posters |
| `data/posters_framed/` | 3610 | Framed posters (Pinterest-ready) |
| `data/posters_clean/` | 3408 | Clean posters (no watermark) |
| `data/publish/ready/` | 3439 | Copies ready for publish |
| `data/cache/` | — | CSV snapshots (movies.csv, movies_clean.csv, pins.csv) |
| `data/logs/` | — | kinopois.log (rotating), events.log, cron.log |

### Cron

```bash
CRON_TZ=Europe/Moscow
0 21 * * * cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois FRAMED_FORCE_REGENERATE=0 FRAMED_REFRESH_SOURCE=0 python3 -m kinopois run-base-pipeline --limit 200 >> /home/nick/kinopois/data/logs/cron.log 2>&1
```

---

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

---

## Base architecture

```
kinopois/
  download/          Kinopoisk API client and poster download
  processing/        CSV cleaning, collages, framing, watermarking
  publishing/         Pin row building, Postgres queue, Pinterest API, autopilot
  cli.py              Click CLI — all commands
  config.py           Env-backed configuration singleton (all local paths)
  interactive.py      Sync questionary-based TUI menu
  logging_setup.py    Python logging with file rotation
  utils.py            Shared CSV and parsing helpers
```

## Data flow

```
Kinopoisk.dev API
  → data/cache/movies.csv (raw API snapshot)
  → SQLite movies_raw / movies_clean / collages (local cache)
  → data/posters_framed/ (framed poster images, local disk)
  → Postgres kinopois_pins (publish queue)
  → n8n / autopilot / Pinterest API (base64 upload, no public URL needed)
```

## Key invariants

- Postgres `kinopois_pins` is the single source of truth for publish state.
- SQLite is a local cache for download/processing data only.
- All images stored locally — Pinterest API uses base64 upload, no remote web server needed.
- `image_url` field stores local relative paths (e.g. `data/posters_framed/11466997.jpg`).
- `pinterest.py` resolves `image_url` to local files via `_resolve_local_image_path()`.

## Base launch on server

```bash
# One-shot pipeline (no Docker needed)
cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois python3 -m kinopois run-base-pipeline --limit 200

# Daemon (autonomous harvest + publish)
PYTHONPATH=/home/nick/kinopois python3 -m kinopois autopilot

# Manual pin pipeline
PYTHONPATH=/home/nick/kinopois python3 -m kinopois pins --limit 200 --sync-queue

# Queue inspection
PYTHONPATH=/home/nick/kinopois python3 -m kinopois queue-ready --limit 5
PYTHONPATH=/home/nick/kinopois python3 -m kinopois db-stats
```