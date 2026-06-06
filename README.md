# kinopois

`kinopois` is a Python CLI for downloading Kinopoisk posters, cleaning movie metadata, and exporting Pinterest-ready rows for automated publishing.

## Project layout

```text
kinopois/
  download/      Kinopoisk API client and poster download
  processing/    CSV cleaning, collages, framing, watermarking
  publishing/    CSV export, Google Sheets sync, SQLite queue, autopilot
  cli.py         Click entrypoint
  config.py      Env-backed configuration
  utils.py       Shared CSV and parsing helpers
docs/            Full project documentation
```

## Main flow

1. `kinopois download` pulls raw movie data into `data/cache/movies.csv`
2. `kinopois process` cleans the dataset into `data/cache/movies_clean.csv`
3. `kinopois export-movie-pins` builds `data/cache/pins.csv`
4. `kinopois sync` pushes rows to Google Sheets

The collage pipeline is separate and writes `data/collages/` plus `data/cache/collages.csv`.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Common commands

```bash
kinopois download --limit 200
kinopois process
kinopois export-movie-pins
kinopois sync
kinopois pins --limit 200 --sync-sheets
kinopois run-prod --limit 200 --max-per-genre 1
```

## Configuration

Copy `.env.example` to `.env` and set at least:

```env
KINOPOISK_API_KEY=...
GOOGLE_CREDS_FILE=credentials/google-service-account.json
GOOGLE_SHEETS_ID=...
```

## Documentation

- [Architecture](docs/architecture.md)
- [Usage](docs/usage.md)
- [Deployment](docs/deployment.md)
- [Data contracts](docs/data-contracts.md)
- [Project notes](docs/INIT.md)
- [Historical context](docs/CLAUDE.md)
