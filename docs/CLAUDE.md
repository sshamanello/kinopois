# CLAUDE.md — kinopois project context

## Project summary

`kinopois` is a Python CLI tool that downloads movie posters from Kinopoisk,
processes metadata, and writes Pinterest-ready pin rows directly into the
Postgres publish queue (`kinopois_pins`) that feeds n8n / autopilot / Pinterest API.

**Everything runs locally** — no remote servers needed. Pinterest API receives
base64-encoded image data from local files via `_resolve_local_image_path()`.

## Architecture

```
Kinopoisk.dev API
    ↓  kinopois download
data/cache/movies.csv          raw API data (kp_id, title, rating_kp, poster_url…)
    ↓  kinopois process
data/cache/movies_clean.csv    cleaned, primary_genre added
    ↓  kinopois run-base-pipeline
data/posters_framed/*.jpg      framed poster images (local disk)
    ↓
Postgres queue (kinopois_pins) → n8n / autopilot → Pinterest API (base64 upload)
```

`export-movie-pins` is still available as an explicit CSV export command, but
it is no longer part of the default publish path.

The **collage pipeline** (`kinopois collage`) runs in parallel and generates
`data/collages/` images + `data/cache/collages.csv`. Both pipelines are
independent — do not mix their output CSVs.

## Key files

| File | Purpose |
|------|---------|
| `kinopois/cli.py` | Click CLI — all commands |
| `kinopois/config.py` | Dataclass config, env vars (no from_env duplication) |
| `kinopois/download/scraper.py` | Kinopoisk API client, poster download |
| `kinopois/processing/processor.py` | Clean movies CSV, add `primary_genre` |
| `kinopois/processing/collage.py` | 2x2 collage image builder |
| `kinopois/processing/marker.py` | Watermark overlay on poster images |
| `kinopois/processing/frame.py` | Framed poster renderer |
| `kinopois/publishing/movie_pins.py` | `build_movie_pin_rows()` + `export_movie_pins_csv()` + SEO generators |
| `kinopois/publishing/collage_export.py` | `export_pinterest_csv()` + `export_simple_collages_csv()` + `export_summary()` |
| `kinopois/publishing/pipeline_steps.py` | Composable pipeline: download → process → upload → publish |
| `kinopois/publishing/postgres_queue.py` | Publish queue (kinopois_pins table) |
| `kinopois/publishing/pinterest.py` | Direct Pinterest API publish client (base64 from local files) |
| `kinopois/publishing/autopilot.py` | Autonomous scheduler |
| `kinopois/publishing/db.py` | SQLite cache (movies_raw, movies_clean, collages) |
| `kinopois/publishing/eventlog.py` | JSONL structured event logger |
| `kinopois/logging_setup.py` | Python logging with rotating file handler |
| `kinopois/interactive.py` | Sync questionary-based TUI menu |
| `kinopois/utils.py` | `read_csv_dict`, `write_csv_dict`, `parse_rating` |

## CSV format

All CSVs use **semicolon delimiter** (`csv_delimiter = ";"`) and **UTF-8 BOM**
encoding (`csv_encoding = "utf-8-sig"`). Never change delimiter without
updating `write_csv_dict` / `read_csv_dict` calls everywhere.

`pins.csv` column order (27 fields):
```
id; image_url; poster_url; title; original_title; year; rating; genres;
primary_genre; kp_url; source_type; description; keywords; category;
board; board_id; status; created_at; posted_at; notes;
public_image_url; remote_image_path; vds_upload_status;
uploaded_at; publish_status; published_at; error_reason
```

## Important invariants

- `_clean_rating`: valid range is `0 < f <= 10` — rejects vote counts (e.g. 46241)
  and date serials that leak from DB `created_at`.
- `_clean_kp_id`: strips trailing `.0` / `.00` from float-ified IDs (e.g. `"1008652.0"` → `"1008652"`).
- `_is_valid_pin_row`: skips row if any of `kp_id`, `title`, `primary_genre` is empty.
- `movies_clean.csv` fieldnames are built from `self.movies[0].keys()` — **do not**
  append `primary_genre` again (it's already added to the dict in the loop).
- Postgres `kinopois_pins` is the single source of truth for publish state.
- SQLite is a local cache for download/processing data only.
- `image_url` in Postgres stores **local relative paths** (e.g. `data/posters_framed/11466997.jpg`).
- `pinterest.py` resolves `image_url` to local files via `_resolve_local_image_path()`
  and uploads base64 — no public URL needed.

## Logging

Three parallel logging channels:
1. `console.print()` via Rich — user-facing CLI output
2. `log_event()` — structured JSONL to `data/logs/events.log`
3. `logger = get_logger(__name__)` — Python logging to `data/logs/kinopois.log` with rotation

## Environment variables (`.env`)

```
KINOPOISK_API_KEY=          # required for download
POSTERS_BASE_URL=           # local path prefix for poster images (default: data/posters)
FRAMED_POSTERS_BASE_URL=    # local path prefix for framed posters (default: data/posters_framed)
BOT_URL=                    # Telegram bot URL used in pin descriptions
PUBLISH_IMAGES_BASE_URL=    # local path prefix for ready-to-publish images (default: data/publish/ready)
FRAMED_FORCE_REGENERATE=0  # reuse existing framed posters (set 1 to force re-render)
FRAMED_REFRESH_SOURCE=0    # skip re-downloading clean poster sources
```

All image paths are **local** — no remote server references. Pinterest uses base64 upload from local files.

## Common commands (on server 192.168.10.122)

```bash
cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois python3 -m kinopois run-base-pipeline --limit 200
cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois python3 -m kinopois pins --limit 200 --sync-queue
cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois python3 -m kinopois export-movie-pins
cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois python3 -m kinopois download --limit 200
cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois python3 -m kinopois process
cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois python3 -m kinopois queue-ready --limit 5
cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois python3 -m kinopois db-stats
```

## Cron (21:00 MSK daily)

```bash
CRON_TZ=Europe/Moscow
0 21 * * * cd /home/nick/kinopois && PYTHONPATH=/home/nick/kinopois FRAMED_FORCE_REGENERATE=0 FRAMED_REFRESH_SOURCE=0 python3 -m kinopois run-base-pipeline --limit 200 >> /home/nick/kinopois/data/logs/cron.log 2>&1
```

## Coding conventions

- No Unicode symbols in console output for Windows compatibility — use plain text or Rich markup.
- `console.print(...)` via `rich.Console` everywhere — no bare `print()`.
- New CLI commands go in `cli.py` using `@main.command(...)`.
- All data helpers (`_clean_*`, `_is_*`, `_build_*`) live in `movie_pins.py`.
- Config is a single dataclass — add new fields as `field(default_factory=lambda: _env_*)`.
- No remote server dependencies — all image operations are local-first.