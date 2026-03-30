"""Configuration management for kinopois."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


@dataclass
class Config:
    """Application configuration."""

    # API
    kinopoisk_api_key: str = field(default_factory=lambda: os.getenv("KINOPOISK_API_KEY", ""))

    # Directories
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "data")))
    posters_dir: Path = field(default_factory=lambda: Path(os.getenv("POSTERS_DIR", "data/posters")))
    collages_dir: Path = field(default_factory=lambda: Path(os.getenv("COLLAGES_DIR", "data/collages")))
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("CACHE_DIR", "data/cache")))

    # Scraping settings
    movies_limit: int = 200
    page_size: int = 50
    rating_min: float = 6.0
    rating_max: float = 10.0
    year_min: int = 2000
    year_max: int = 2025

    # Collage settings
    collage_tile_width: int = 500
    collage_tile_height: int = 750
    collage_max_per_genre: Optional[int] = None

    # Watermark / marking
    watermark_text: str = "@TopTrailer82Bot"
    watermark_position: str = "bottom"  # bottom, top, corner

    # Export
    bot_url: str = "https://t.me/TopTrailer82Bot"
    base_image_url: str = "https://sshamanello.ru/collages"
    posters_base_url: str = field(default_factory=lambda: os.getenv("POSTERS_BASE_URL", "https://sshamanello.ru/posters"))

    # Google Sheets integration
    google_creds_file: str = field(default_factory=lambda: os.getenv("GOOGLE_CREDS_FILE", ""))
    google_sheets_id: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEETS_ID", ""))
    google_sheets_tab: str = field(default_factory=lambda: os.getenv("GOOGLE_SHEETS_TAB", "pins"))

    # Pinterest
    pinterest_board_id: str = field(default_factory=lambda: os.getenv("PINTEREST_BOARD_ID", ""))

    # CSV settings
    csv_delimiter: str = ";"
    csv_encoding: str = "utf-8-sig"

    def __post_init__(self):
        """Create directories if they don't exist."""
        self.posters_dir.mkdir(parents=True, exist_ok=True)
        self.collages_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.posters_base_url = self.posters_base_url.rstrip("/")

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        return cls(
            kinopoisk_api_key=os.getenv("KINOPOISK_API_KEY", ""),
            data_dir=Path(os.getenv("DATA_DIR", "data")),
            posters_dir=Path(os.getenv("POSTERS_DIR", "data/posters")),
            collages_dir=Path(os.getenv("COLLAGES_DIR", "data/collages")),
            cache_dir=Path(os.getenv("CACHE_DIR", "data/cache")),
            collage_tile_width=int(os.getenv("COLLAGE_TILE_WIDTH", "500")),
            collage_tile_height=int(os.getenv("COLLAGE_TILE_HEIGHT", "750")),
            collage_max_per_genre=int(os.getenv("COLLAGE_MAX_PER_GENRE", "")) if os.getenv("COLLAGE_MAX_PER_GENRE") else None,
            watermark_text=os.getenv("WATERMARK_TEXT", "@TopTrailer82Bot"),
            watermark_position=os.getenv("WATERMARK_POSITION", "bottom"),
            bot_url=os.getenv("BOT_URL", "https://t.me/TopTrailer82Bot"),
            base_image_url=os.getenv("BASE_IMAGE_URL", "https://sshamanello.ru/collages"),
            posters_base_url=os.getenv("POSTERS_BASE_URL", "https://sshamanello.ru/posters"),
            google_creds_file=os.getenv("GOOGLE_CREDS_FILE", ""),
            google_sheets_id=os.getenv("GOOGLE_SHEETS_ID", ""),
            google_sheets_tab=os.getenv("GOOGLE_SHEETS_TAB", "pins"),
            pinterest_board_id=os.getenv("PINTEREST_BOARD_ID", ""),
        )


# Global config instance
config = Config.from_env()
