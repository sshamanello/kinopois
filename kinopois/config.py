"""Configuration management for kinopois.

All settings are read from environment variables via dataclass field defaults.
The module-level `config` singleton is created once at import time.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _env_bool(key: str, default: str = "0") -> bool:
    """Read a boolean from env: '1'/'true'/'yes' → True, else False."""
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes")


def _env_int(key: str, default: str = "0") -> int:
    """Read an integer from env with a fallback default."""
    return int(os.getenv(key, default))


def _env_str(key: str, default: str = "") -> str:
    """Read a string from env with a fallback default."""
    return os.getenv(key, default)


def _env_path(key: str, default: str) -> Path:
    """Read a file-system path from env with a fallback default."""
    return Path(os.getenv(key, default))


@dataclass
class Config:
    """Application configuration — all values come from environment variables."""

    # ── API ──────────────────────────────────────────────────────────────────
    kinopoisk_api_key: str = field(default_factory=lambda: _env_str("KINOPOISK_API_KEY"))
    kinopoisk_api_url: str = field(default_factory=lambda: _env_str("KINOPOISK_API_URL", "https://api.poiskkino.dev/v1.4/movie"))
    kinopoisk_resolve_ips: str = field(default_factory=lambda: _env_str("KINOPOISK_RESOLVE_IPS"))

    # ── Directories ──────────────────────────────────────────────────────────
    data_dir: Path = field(default_factory=lambda: _env_path("DATA_DIR", "data"))
    posters_dir: Path = field(default_factory=lambda: _env_path("POSTERS_DIR", "data/posters"))
    framed_source_posters_dir: Path = field(default_factory=lambda: _env_path("FRAMED_SOURCE_POSTERS_DIR", "data/posters_clean"))
    framed_posters_dir: Path = field(default_factory=lambda: _env_path("FRAMED_POSTERS_DIR", "data/posters_framed"))
    collages_dir: Path = field(default_factory=lambda: _env_path("COLLAGES_DIR", "data/collages"))
    cache_dir: Path = field(default_factory=lambda: _env_path("CACHE_DIR", "data/cache"))

    # ── Scraping settings ────────────────────────────────────────────────────
    movies_limit: int = 200
    page_size: int = 50
    rating_min: float = 6.0
    rating_max: float = 10.0
    year_min: int = 2000
    year_max: int = 2025

    # ── Collage settings ─────────────────────────────────────────────────────
    collage_tile_width: int = 500
    collage_tile_height: int = 750
    collage_max_per_genre: Optional[int] = None

    # ── Watermark / marking ──────────────────────────────────────────────────
    watermark_text: str = "@TopTrailer82Bot"
    watermark_position: str = "bottom"  # bottom, top, corner

    # ── Export / URLs ─────────────────────────────────────────────────────────
    bot_url: str = "https://t.me/TopTrailer82Bot"
    base_image_url: str = field(default_factory=lambda: _env_str("BASE_IMAGE_URL", "data/collages"))
    posters_base_url: str = field(default_factory=lambda: _env_str("POSTERS_BASE_URL", "data/posters"))
    framed_posters_base_url: str = field(default_factory=lambda: _env_str("FRAMED_POSTERS_BASE_URL", "data/posters_framed"))

    # ── Framed poster settings ────────────────────────────────────────────────
    use_framed_posters: bool = field(default_factory=lambda: _env_bool("USE_FRAMED_POSTERS", "1"))
    framed_refresh_source: bool = field(default_factory=lambda: _env_bool("FRAMED_REFRESH_SOURCE", "1"))
    framed_force_regenerate: bool = field(default_factory=lambda: _env_bool("FRAMED_FORCE_REGENERATE", "1"))

    # ── Publish / image upload ───────────────────────────────────────────────
    publish_images_dir: Path = field(default_factory=lambda: _env_path("PUBLISH_IMAGES_DIR", "data/publish/ready"))
    publish_images_base_url: str = field(default_factory=lambda: _env_str("PUBLISH_IMAGES_BASE_URL", "data/publish/ready"))
    publish_images_cleanup_enabled: bool = field(default_factory=lambda: _env_bool("PUBLISH_IMAGES_CLEANUP_ENABLED", "1"))
    publish_images_retention_days: int = field(default_factory=lambda: _env_int("PUBLISH_IMAGES_RETENTION_DAYS", "21"))

    # ── Postgres queue ───────────────────────────────────────────────────────
    queue_db_host: str = field(default_factory=lambda: _env_str("QUEUE_DB_HOST", "127.0.0.1"))
    queue_db_port: int = field(default_factory=lambda: _env_int("QUEUE_DB_PORT", "5432"))
    queue_db_name: str = field(default_factory=lambda: _env_str("QUEUE_DB_NAME", "pinterest"))
    queue_db_user: str = field(default_factory=lambda: _env_str("QUEUE_DB_USER", "pinterest"))
    queue_db_password: str = field(default_factory=lambda: _env_str("QUEUE_DB_PASSWORD"))
    queue_db_sslmode: str = field(default_factory=lambda: _env_str("QUEUE_DB_SSLMODE", "disable"))

    # ── Pinterest ─────────────────────────────────────────────────────────────
    pinterest_access_token: str = field(default_factory=lambda: _env_str("PINTEREST_ACCESS_TOKEN"))
    pinterest_board_id: str = field(default_factory=lambda: _env_str("PINTEREST_BOARD_ID"))

    # ── CSV settings ──────────────────────────────────────────────────────────
    csv_delimiter: str = ";"
    csv_encoding: str = "utf-8-sig"

    # ── Autopilot scheduler ──────────────────────────────────────────────────
    autopilot_enabled: bool = field(default_factory=lambda: _env_bool("AUTOPILOT_ENABLED", "0"))
    autopilot_download_limit_per_day: int = field(default_factory=lambda: _env_int("AUTOPILOT_DOWNLOAD_LIMIT_PER_DAY", "200"))
    autopilot_posts_per_day: int = field(default_factory=lambda: _env_int("AUTOPILOT_POSTS_PER_DAY", "3"))
    autopilot_publish_attempts_per_slot: int = field(default_factory=lambda: _env_int("AUTOPILOT_PUBLISH_ATTEMPTS_PER_SLOT", "5"))
    autopilot_enable_publish: bool = field(default_factory=lambda: _env_bool("AUTOPILOT_ENABLE_PUBLISH", "1"))
    autopilot_slot_hours: str = field(default_factory=lambda: _env_str("AUTOPILOT_SLOT_HOURS", "10,15,20"))
    autopilot_slot_jitter_min: int = field(default_factory=lambda: _env_int("AUTOPILOT_SLOT_JITTER_MIN", "20"))
    autopilot_loop_sleep_sec: int = field(default_factory=lambda: _env_int("AUTOPILOT_LOOP_SLEEP_SEC", "30"))
    autopilot_state_file: Path = field(default_factory=lambda: _env_path("AUTOPILOT_STATE_FILE", "data/cache/autopilot_state.json"))
    autopilot_publish_command: str = field(default_factory=lambda: _env_str("AUTOPILOT_PUBLISH_COMMAND"))
    autopilot_sync_queue: bool = field(default_factory=lambda: _env_bool("AUTOPILOT_SYNC_QUEUE", "1"))

    # ── Telegram alerts ──────────────────────────────────────────────────────
    telegram_bot_token: str = field(default_factory=lambda: _env_str("TELEGRAM_BOT_TOKEN"))
    telegram_chat_id: str = field(default_factory=lambda: _env_str("TELEGRAM_CHAT_ID"))

    # ── Logging ───────────────────────────────────────────────────────────────
    log_dir: Path = field(default_factory=lambda: _env_path("LOG_DIR", "data/logs"))
    log_level: str = field(default_factory=lambda: _env_str("LOG_LEVEL", "INFO"))

    def __post_init__(self):
        """Create directories if they don't exist; normalise path strings."""
        self.posters_dir.mkdir(parents=True, exist_ok=True)
        self.collages_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.framed_source_posters_dir.mkdir(parents=True, exist_ok=True)
        self.framed_posters_dir.mkdir(parents=True, exist_ok=True)
        self.publish_images_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.posters_base_url = self.posters_base_url.rstrip("/")
        self.framed_posters_base_url = self.framed_posters_base_url.rstrip("/")
        self.publish_images_base_url = self.publish_images_base_url.rstrip("/")


# ── Global config singleton ──────────────────────────────────────────────────
config = Config()