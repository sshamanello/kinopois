# kinopois

CLI tool for downloading movie posters from Kinopoisk, building Pinterest-ready pin rows, and syncing them to Google Sheets for automated publishing via n8n.

## Features

- Download movie posters from Kinopoisk.dev API
- Clean and process movie metadata
- Export Pinterest-ready CSV (`pins.csv`) with titles, descriptions, keywords, boards
- Sync pins to Google Sheets (upsert by ID)
- Create 2x2 collages grouped by genre
- Full pipeline in one command
- Autonomous scheduler mode (daily harvest + timed posting slots)
- Docker + cron deployment

## Architecture

```
Kinopoisk.dev API
    |  kinopois download
data/cache/movies.csv          raw API data
    |  kinopois process
data/cache/movies_clean.csv    cleaned, primary_genre added
    |  kinopois export-movie-pins
data/cache/pins.csv            one row per poster, all Pinterest fields
    |  kinopois sync-sheets
Google Sheets (tab: pins)      n8n reads rows, posts to Pinterest
```

The collage pipeline (`kinopois run-prod`) runs independently and produces
`data/collages/` images + `data/cache/collages.csv`.

## Installation

### Requirements

- Python 3.10+

### Install from source

```bash
cd kinopois
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

### Dependencies

```
click requests pillow python-dotenv rich questionary gspread google-auth
```

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# Required
KINOPOISK_API_KEY=your_api_key_here

# URL prefix for poster images (self-hosted or CDN)
POSTERS_BASE_URL=https://example.com/posters

# Telegram bot link used in pin descriptions
BOT_URL=https://t.me/your_bot

# Google Sheets (optional, for sync-sheets)
GOOGLE_CREDS_FILE=credentials/service_account.json
GOOGLE_SHEETS_ID=your_spreadsheet_id
GOOGLE_SHEETS_TAB=pins
```

Get your Kinopoisk API key at [kinopoisk.dev](https://kinopoisk.dev/).

## Usage

### Main pipeline — pins + Google Sheets

```bash
# Full pipeline: download -> process -> export pins.csv -> sync to Sheets
kinopois pins --limit 200 --sync-sheets

# Without Sheets sync
kinopois pins --limit 200

# Re-export pins.csv from existing movies_clean.csv
kinopois export-movie-pins

# Push existing pins.csv to Google Sheets
kinopois sync
```

### Autonomous server mode

```bash
# One pass (useful for health-check and cron testing)
kinopois autopilot-once

# Long-running daemon:
# - harvest once per day (append mode, up to AUTOPILOT_DOWNLOAD_LIMIT_PER_DAY)
# - then tries publish slots by AUTOPILOT_SLOT_HOURS
kinopois autopilot
```

Autopilot is stateful and keeps `data/cache/autopilot_state.json`.
It is designed for long-term backlog growth: daily harvest appends new movies
to `movies.csv` instead of replacing old rows.
By default autopilot publishes directly to Pinterest API using
`PINTEREST_ACCESS_TOKEN` + `board_id` from row (or fallback `PINTEREST_BOARD_ID`).
`AUTOPILOT_PUBLISH_COMMAND` is optional override for custom external posting.

### Collage pipeline

```bash
# Full collage pipeline: download -> process -> collages -> export
kinopois run-prod --limit 200 --max-per-genre 1

# With watermark
kinopois run-prod --limit 200 --max-per-genre 1 --watermark-text "@YourBot"
```

### Individual commands

```bash
# Download posters from Kinopoisk
kinopois download --limit 200

# Clean and process movies.csv
kinopois process

# Create 2x2 collages by genre
kinopois collage --watermark "@YourBot" --max-per-genre 5

# Add watermark to poster images
kinopois mark data/posters --text "@YourBot" --position bottom

# Show project info (file counts, sizes)
kinopois info

# Clean generated data
kinopois clean --cache      # remove CSVs
kinopois clean --collages   # remove collage images
kinopois clean --all        # remove everything
```

## Google Sheets setup

1. Create a Google Cloud service account with Sheets API access.
2. Download the JSON key to `credentials/service_account.json`.
3. Share your spreadsheet with the service account email.
4. Set `GOOGLE_CREDS_FILE`, `GOOGLE_SHEETS_ID`, `GOOGLE_SHEETS_TAB` in `.env`.
5. Run `kinopois sync-sheets` — it will create the header row and upsert all pins.

The sync is idempotent: rows are matched by `id`; existing rows are updated,
new ones are appended.

## Docker deployment

```bash
docker compose build
docker compose run --rm kinopois run-pins --limit 200 --sync-sheets
```

`data/` and `credentials/` are volume-mounted and never baked into the image.

### Cron (daily at 09:00)

```bash
bash deploy/cron-setup.sh
```

## Project structure

```
kinopois/
+-- kinopois/
|   +-- cli.py            CLI commands (Click)
|   +-- config.py         Config dataclass, env vars
|   +-- scraper.py        Kinopoisk.dev API client
|   +-- processor.py      Clean movies.csv, add primary_genre
|   +-- export.py         export_movie_pins_csv() and collage exporters
|   +-- sheets.py         sync_pins_to_sheets() - Google Sheets upsert
|   +-- collage.py        2x2 collage image builder
|   +-- marker.py         Watermark overlay
|   +-- db.py             SQLite publish queue (legacy)
|   +-- utils.py          read_csv_dict, write_csv_dict, parse_rating
+-- data/                  (gitignored)
|   +-- posters/
|   +-- collages/
|   +-- cache/
+-- credentials/           (gitignored) Google service account keys
+-- deploy/                cron-setup.sh, Dockerfile, docker-compose.yml
+-- .env.example
+-- pyproject.toml
```

## CSV format

All CSVs use semicolon delimiter and UTF-8 BOM encoding.

`pins.csv` columns (20 fields):
```
id; image_url; poster_url; title; original_title; year; rating; genres;
primary_genre; kp_url; source_type; description; keywords; category;
board; board_id; status; created_at; posted_at; notes
```

## CLI reference

| Command | Description |
|---------|-------------|
| `kinopois run-pins` | Full pin pipeline (download + process + export + optional sync) |
| `kinopois pins` | Full pin pipeline (download + process + export + optional sync) |
| `kinopois export-movie-pins` | Re-export pins.csv from existing data |
| `kinopois sync` | Push pins.csv to Google Sheets |
| `kinopois autopilot-once` | Run one autonomous tick (harvest + due slots) |
| `kinopois autopilot` | Run autonomous daemon forever |
| `kinopois run-prod` | Full collage pipeline |
| `kinopois download` | Download movies from Kinopoisk |
| `kinopois process` | Clean and process movies.csv |
| `kinopois collage` | Create 2x2 collages |
| `kinopois mark` | Add watermarks to images |
| `kinopois info` | Show project info |
| `kinopois clean` | Remove generated data |
| `kinopois interactive` | Interactive menu mode |

## n8n integration

Recommended flow in n8n:

1. `kinopois run-pins --limit 200 --sync-sheets` (scheduled, daily)
2. Google Sheets trigger: new rows with `status = ready`
3. Pinterest publish node
4. Update row `status` to `posted`, fill `posted_at` and `notes` (pin URL)

## Development

```bash
pytest
black kinopois/
ruff check kinopois/
```

## License

MIT
