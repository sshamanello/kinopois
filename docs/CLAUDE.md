# CLAUDE.md — kinopois project context

## Project summary

`kinopois` is a Python CLI tool that downloads movie posters from Kinopoisk,
processes metadata, and exports Pinterest-ready pin rows (CSV) that feed an
automated publishing pipeline via Postgres queue → n8n → Pinterest API.

## Architecture

```
Kinopoisk.dev API
    ↓  kinopois download
data/cache/movies.csv          raw API data (kp_id, title, rating_kp, poster_url…)
    ↓  kinopois process
data/cache/movies_clean.csv    cleaned, primary_genre added
    ↓  kinopois export-movie-pins
data/cache/pins.csv            one row per poster, all Pinterest fields
    ↓  kinopois queue-sync
Postgres queue (`kinopois_pins`) n8n reads rows, posts to Pinterest, marks posted
```

The **collage pipeline** (`kinopois run-prod`) runs in parallel and generates
`data/collages/` images + `data/cache/collages.csv`. Both pipelines are
independent — do not mix their output CSVs.

## Key files

| File | Purpose |
|------|---------|
| `kinopois/cli.py` | Click CLI — all commands |
| `kinopois/config.py` | Dataclass config, env vars, `config` singleton |
| `kinopois/scraper.py` | Kinopoisk.dev API client, poster download |
| `kinopois/processor.py` | Clean movies CSV, add `primary_genre` |
| `kinopois/export.py` | `export_movie_pins_csv()` + collage exporters |
| `kinopois/db.py` | Local CSV/SQLite cache helpers |
| `kinopois/publishing/postgres_queue.py` | Postgres publish queue helpers |
| `kinopois/collage.py` | 2×2 collage image builder |
| `kinopois/utils.py` | `read_csv_dict`, `write_csv_dict`, `parse_rating` |

## CSV format

All CSVs use **semicolon delimiter** (`csv_delimiter = ";"`) and **UTF-8 BOM**
encoding (`csv_encoding = "utf-8-sig"`). Never change delimiter without
updating `write_csv_dict` / `read_csv_dict` calls everywhere.

`pins.csv` column order (20 fields):
```
id; image_url; poster_url; title; original_title; year; rating; genres;
primary_genre; kp_url; source_type; description; keywords; category;
board; board_id; status; created_at; posted_at; notes
```

## Important invariants

- `_clean_rating`: valid range is `0 < f <= 10` — rejects vote counts (e.g. 46241)
  and date serials that leak from DB `created_at`.
- `_clean_kp_id`: strips trailing `.0` / `.00` from float-ified IDs (e.g. `"1008652.0"` → `"1008652"`).
- `_is_valid_pin_row`: skips row if any of `kp_id`, `title`, `primary_genre` is empty.
- `movies_clean.csv` fieldnames are built from `self.movies[0].keys()` — **do not**
  append `primary_genre` again (it's already added to the dict in the loop).

## Environment variables (`.env`)

```
KINOPOISK_API_KEY=          # required for download
POSTERS_BASE_URL=           # public URL prefix for poster images (self-hosted)
BOT_URL=                    # Telegram bot URL used in pin descriptions
QUEUE_DB_HOST=127.0.0.1     # local Postgres host used by n8n and kinopois
QUEUE_DB_PORT=5432          # local Postgres port
QUEUE_DB_NAME=pinterest     # queue database name
QUEUE_DB_USER=pinterest     # queue database user
QUEUE_DB_PASSWORD=...       # queue database password
```

## Docker / deployment

```bash
docker compose build
docker compose run --rm kinopois queue-sync
bash deploy/cron-setup.sh   # cron at 09:00 daily
```

`data/` and `credentials/` are volume-mounted — never baked into the image.

## Common commands

```bash
kinopois run-pins --limit 200                 # full pipeline
kinopois export-movie-pins                    # re-export pins.csv only
kinopois queue-sync                           # import pins.csv into Postgres queue
kinopois download --limit 200                 # download only
kinopois process                              # clean movies.csv
```

## Coding conventions

- No Unicode symbols (✓ ⚠) in console output — Windows terminal is cp1251.
  Use plain text or Rich markup tags only.
- `console.print(...)` via `rich.Console` everywhere — no bare `print()`.
- New CLI commands go in `cli.py` using `@main.command(...)`.
- All data helpers (`_clean_*`, `_is_*`, `_build_*`) live in `export.py`.
