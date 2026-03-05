# Kinopoisk Poster Downloader

CLI utility for downloading movie posters from Kinopoisk and creating beautiful collages with watermarks.

## Features

- 🎥 Download movie posters from Kinopoisk.dev API
- 🔄 Process and clean movie data
- 🖼️ Create 2x2 collages with automatic layout
- ✏️ Add watermarks to individual posters and collages
- 📤 Export to various formats (Pinterest CSV, simple CSV)
- 🎮 **Interactive menu mode** with keyboard navigation
- ⚡ Full pipeline automation

## Installation

### Requirements

- Python 3.10+

### Install from source

```bash
# Clone or navigate to project directory
cd kinopois

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .
```

### Manual installation

```bash
pip install click requests pillow python-dotenv rich questionary
```

## Configuration

1. Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

2. Edit `.env` and set your Kinopoisk API key:

```env
KINOPOISK_API_KEY=your_api_key_here
```

Get your API key at [kinopoisk.dev](https://kinopoisk.dev/).

## Usage

### Interactive Mode (Recommended!)

Simply run:

```bash
kinopois interactive
```

Or just:

```bash
kinopois
```

This launches an interactive menu where you can:
- Navigate with **arrow keys** ↑↓
- Select with **Enter**
- Go back with **Esc**
- See real-time project status

**Interactive menu includes:**
- 📥 Download posters
- 🔄 Process data
- 🖼️ Create collages
- ✏️ Mark posters with watermarks
- 📤 Export data
- 🗑️ Clean data
- ⚙️ Settings

### Command-Line Mode

#### Quick Start - Full Pipeline

```bash
kinopois run --all --limit 200
```

#### Production Pipeline (for n8n queue)

```bash
# watermark optional; one collage per genre (4 titles)
kinopois run-prod --limit 200 --max-per-genre 1 --watermark-text "@YourWatermark"

# without watermark
kinopois run-prod --limit 200 --max-per-genre 1
```

This will:
1. Download 200 movies with posters
2. Process and clean the data
3. Create collages grouped by genre
4. Export to Pinterest-compatible CSV

#### Individual Commands

##### Download posters

```bash
kinopois download --limit 200
```

##### Process data

```bash
kinopois process
```

##### Create collages

```bash
kinopois collage --watermark "@YourBot" --max-per-genre 5
```

##### Add watermark to posters

```bash
kinopois mark data/posters --text "@YourBot" --position bottom
```

##### Export data

```bash
# Pinterest format
kinopois export --format pinterest

# Simple CSV
kinopois export --format simple

# Summary statistics
kinopois export --format summary
```

##### Show project info

```bash
kinopois info
```

##### Clean generated data

```bash
# Clean cache only
kinopois clean --cache

# Clean collages only
kinopois clean --collages

# Clean everything
kinopois clean --all
```

## Project Structure

```
kinopois/
├── kinopois/              # Main package
│   ├── __init__.py
│   ├── cli.py            # CLI commands (Click)
│   ├── interactive.py    # Interactive menu (questionary)
│   ├── config.py         # Configuration management
│   ├── scraper.py        # Kinopoisk API client
│   ├── processor.py      # Data processing
│   ├── collage.py        # Collage creation
│   ├── marker.py         # Watermark marking
│   ├── export.py         # Export functionality
│   └── utils.py          # Utility functions
├── data/                  # Data directory (gitignored)
│   ├── posters/          # Downloaded posters
│   ├── collages/         # Generated collages
│   └── cache/            # CSV cache files
├── tests/                 # Tests
├── .env.example          # Example environment variables
├── .gitignore
├── pyproject.toml        # Project metadata
└── README.md
```

## Data Files

The project generates several CSV files in `data/cache/`:

- `movies.csv` - Raw data from Kinopoisk API
- `movies_clean.csv` - Cleaned data with primary_genre
- `collages.csv` - Collage metadata with film titles
- `pins.csv` - Pinterest-ready export format

## Development

### Running tests

```bash
pytest
```

### Code formatting

```bash
black kinopois/
ruff check kinopois/
```

## n8n + Pinterest (SQLite queue)

Для автоматической публикации без HTTP-слоя:

```bash
# 1) Сгенерировать pins.csv как раньше
kinopois export --format pinterest

# 2) Инициализировать БД и синхронизировать ВСЕ артефакты (movies/clean/collages/pins)
kinopois db-init
kinopois db-sync-all

# 3) Проверить состояние БД
kinopois db-stats

# 4) Получить ready jobs (JSON для n8n)
kinopois queue-ready --limit 20

# 4) После успешной публикации
kinopois queue-posted --job-id 1 --pin-id <pinterest_pin_id>

# 5) Если ошибка публикации
kinopois queue-failed --job-id 1 --error "Pinterest API 429"
```

Рекомендуемый flow в n8n:
1. Execute Command: `kinopois queue-ready --limit 20`
2. Split items
3. Pinterest publish node
4. Execute Command на каждый item:
   - success: `kinopois queue-posted --job-id {{$json.id}} --pin-id {{$json.pin_id}}`
   - fail: `kinopois queue-failed --job-id {{$json.id}} --error "{{$json.error}}"`

## CLI Commands Reference

| Command | Description | Mode |
|---------|-------------|------|
| `kinopois` | Launch interactive menu | Interactive |
| `kinopois interactive` | Launch interactive menu | Interactive |
| `kinopois download` | Download movies from Kinopoisk | CLI |
| `kinopois process` | Clean and process movie data | CLI |
| `kinopois collage` | Create 2x2 collages | CLI |
| `kinopois mark` | Add watermarks to images | CLI |
| `kinopois export` | Export to various formats | CLI |
| `kinopois run` | Run full pipeline | CLI |
| `kinopois clean` | Clean generated data | CLI |
| `kinopois info` | Show project information | CLI |

## Interactive Mode Features

- **Keyboard navigation** - Use arrow keys to navigate
- **Real-time status** - See posters/collages count at a glance
- **Smart defaults** - Pre-filled values from config
- **Validation** - Input validation for all parameters
- **Visual feedback** - Rich formatted output with colors
- **Settings editor** - Change API key, watermark, limits from menu

## License

MIT
