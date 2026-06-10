"""Build and export individual movie poster pin rows.

This module creates Pinterest-ready pin rows from the movies_clean CSV.
Each movie becomes one pin with SEO-optimized title, description, keywords,
and the correct board assignment.
"""

import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console

from kinopois.config import config
from kinopois.processing.frame import render_framed_poster
from kinopois.publishing.postgres_queue import sync_pin_rows
from kinopois.utils import read_csv_dict, write_csv_dict
from kinopois.logging_setup import get_logger
logger = get_logger(__name__)

console = Console()


# ── Validation helpers ────────────────────────────────────────────────────────

_NAN = {"", "nan", "none", "null", "n/a"}
_GENRE_SEP = re.compile(r"[,;/|]+")


def _is_nan(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().lower() in _NAN


def _clean_kp_id(value) -> str:
    """Return kp_id as clean integer string. Handles '1008652.0', '1008652.00'."""
    s = str(value).strip()
    if s.lower() in _NAN:
        return ""
    if re.match(r"^\d+(\.0+)?$", s):
        return str(int(float(s)))
    return s


def _clean_str(value, default="") -> str:
    if _is_nan(value):
        return default
    return str(value).strip()


def _clean_rating(value, default="—") -> str:
    try:
        f = float(str(value).strip())
        return f"{f:.1f}" if 0 < f <= 10 else default
    except Exception:
        return default


def _clean_year(value, default="") -> str:
    if _is_nan(value):
        return default
    s = str(value).strip()
    return s if s.isdigit() and len(s) == 4 else default


def _normalize_genre(value) -> str:
    """Lowercase, take first genre. Handles ',', ';', '/', '|' separators."""
    s = str(value).strip().lower()
    if s in _NAN:
        return ""
    parts = _GENRE_SEP.split(s)
    return parts[0].strip() if parts else ""


def _build_keywords(*parts) -> str:
    """Deduplicated, NaN-free, max-500-char comma-joined keywords."""
    seen: set = set()
    result: list = []
    for p in parts:
        if p is None:
            continue
        p = str(p).strip()
        if p and p.lower() not in _NAN and p not in seen:
            seen.add(p)
            result.append(p)
    return ",".join(result)[:500]


def _is_valid_pin_row(kp_id: str, title: str, primary_genre: str) -> bool:
    return bool(kp_id and title and primary_genre)


def _clip_title(value: str, limit: int = 100) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"


# ── SEO title/description generation ─────────────────────────────────────────

_GENRE_LABELS = {
    "драма": "драмы",
    "комедия": "комедии",
    "триллер": "триллеры",
    "мелодрама": "мелодрамы",
    "боевик": "боевики",
    "ужасы": "ужасы",
    "фантастика": "фантастика",
    "фэнтези": "фэнтези",
    "криминал": "криминал",
    "мультфильм": "мультфильмы",
    "аниме": "аниме",
    "документальный": "документальное кино",
    "детектив": "детективы",
    "короткометражка": "короткометражные фильмы",
    "концерт": "концерты",
    "реальное тв": "реалити-шоу",
}

_SEO_TITLE_TEMPLATES = [
    "Что посмотреть вечером: {title} ({year}) | {genre_label}",
    "{title} ({year}) — фильм на вечер | {genre_label}",
    "Топ находка: {title} ({year}) — {genre_label}, рейтинг {score}",
    "{genre_label}: {title} ({year}) | рейтинг {score}",
    "{title} — рекомендация в жанре {genre_label} ({year})",
    "Лучшие {genre_label}: {title} ({year})",
    "{title} ({year}) — что посмотреть сегодня | {genre_label}",
    "Сохраните в подборку: {title} — {genre_label}, рейтинг {score}",
]

_SEO_DESCRIPTION_TEMPLATES = [
    "{title} ({year_label}) — {genre}. Рейтинг КП: {score}. Что посмотреть вечером: сохраняйте пин и переходите в бота за подборками {bot_url}",
    "Ищете хороший {genre}? {title} ({year_label}) с рейтингом {score}. Больше фильмов по настроению в Telegram: {bot_url}",
    "{title} — фильм в жанре {genre}, рейтинг Кинопоиска {score}. Подборки на вечер и похожее кино: {bot_url}",
    "{genre} на вечер: {title} ({year_label}), рейтинг {score}. Сохраняйте идею и забирайте новые рекомендации в боте {bot_url}",
    "Что посмотреть сегодня: {title} ({year_label}), жанр — {genre}, рейтинг КП {score}. Ещё варианты в боте: {bot_url}",
    "{title} ({year_label}) — {genre} для вашей подборки. Рейтинг: {score}. Нажмите в бота и получите следующую идею: {bot_url}",
]


def _build_seo_title(title: str, genre: str, year: str, rating: str, i: int) -> str:
    genre_label = _GENRE_LABELS.get(genre, genre)
    score = rating if rating != "—" else "без рейтинга"
    t = _SEO_TITLE_TEMPLATES[i % len(_SEO_TITLE_TEMPLATES)]
    out = t.format(
        title=title, genre=genre, genre_label=genre_label,
        year=year or "год неизвестен", rating=rating, score=score,
    )
    return _clip_title(out, 100)


def _build_seo_description(title: str, genre: str, year: str, rating: str, bot_url: str, i: int) -> str:
    year_label = year or "год неизвестен"
    score = rating if rating != "—" else "без рейтинга"
    t = _SEO_DESCRIPTION_TEMPLATES[i % len(_SEO_DESCRIPTION_TEMPLATES)]
    out = t.format(title=title, genre=genre, year_label=year_label, score=score, bot_url=bot_url)
    return out[:800]


# ── Board mapping ─────────────────────────────────────────────────────────────

GENRE_BOARD_MAP = {
    "драма": "Драмы",
    "комедия": "Комедии",
    "триллер": "Триллеры",
    "мелодрама": "Мелодрамы",
    "боевик": "Боевики",
    "аниме": "Аниме",
    "мультфильм": "Мультфильмы",
    "документальный": "Документальное кино",
    "ужасы": "Ужасы",
    "фантастика": "Фантастика",
    "фэнтези": "Фэнтези",
    "криминал": "Криминал",
    "мюзикл": "Мюзиклы",
    "концерт": "Концерты",
    "реальное тв": "Реалити-шоу",
    "короткометражка": "Короткометражки",
}

_MOVIE_PIN_FIELDNAMES = [
    "id", "image_url", "poster_url", "title", "original_title",
    "year", "rating", "genres", "primary_genre", "kp_url", "source_type",
    "description", "keywords", "category", "board", "board_id",
    "status", "created_at", "posted_at", "notes",
    "public_image_url", "remote_image_path", "vds_upload_status",
    "uploaded_at", "publish_status", "published_at", "error_reason",
]


# ── Poster refresh ───────────────────────────────────────────────────────────

def _refresh_clean_poster(kp_id: str, poster_url: str, fallback_path: Path) -> Path:
    """Re-download the clean (unwatermarked) poster from poster_url if configured."""
    if not config.framed_refresh_source or not poster_url:
        return fallback_path

    clean_path = config.framed_source_posters_dir / f"{kp_id}.jpg"
    try:
        response = requests.get(poster_url, timeout=20)
        response.raise_for_status()
        clean_path.write_bytes(response.content)
        return clean_path
    except Exception:
        return fallback_path


# ── Public API ────────────────────────────────────────────────────────────────

def build_movie_pin_rows(
    input_csv: Path,
    limit: Optional[int] = None,
    posters_dir: Optional[Path] = None,
) -> tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Build individual movie poster pin rows from cleaned movie CSV.

    Each movie in movies_clean.csv becomes one pin row.
    Rows with missing kp_id/title/genre or absent poster file are skipped.

    Returns:
        Tuple of (rows, skip_stats).
    """
    now_str = datetime.now().isoformat(timespec="seconds")
    rows = read_csv_dict(input_csv, config.csv_delimiter, config.csv_encoding)

    pins: List[Dict[str, Any]] = []
    seen_ids: set = set()
    skip = {"invalid": 0, "missing_poster": 0, "duplicate": 0}
    poster_dir = Path(posters_dir or config.posters_dir)

    for i, row in enumerate(rows):
        if limit and len(pins) >= limit:
            break

        kp_id = _clean_kp_id(row.get("kp_id", ""))
        movie_title = _clean_str(row.get("title"))
        primary_genre = _normalize_genre(row.get("primary_genre") or row.get("genres"))

        if not _is_valid_pin_row(kp_id, movie_title, primary_genre):
            skip["invalid"] += 1
            continue

        poster_path = poster_dir / f"{kp_id}.jpg"
        if not poster_path.exists():
            skip["missing_poster"] += 1
            continue

        if kp_id in seen_ids:
            skip["duplicate"] += 1
            continue
        seen_ids.add(kp_id)

        original_title = _clean_str(row.get("original_title"))
        year = _clean_year(row.get("year"))
        rating = _clean_rating(row.get("rating_kp"))
        seo_title = _build_seo_title(movie_title, primary_genre, year, rating, i)
        poster_url = _clean_str(row.get("poster_url"))
        genres = _clean_str(row.get("genres"))
        board = GENRE_BOARD_MAP.get(primary_genre, "Фильмы")
        kp_url = f"https://www.kinopoisk.ru/film/{kp_id}/"
        image_url = f"{config.posters_base_url}/{kp_id}.jpg"
        if config.use_framed_posters:
            source_for_frame = _refresh_clean_poster(kp_id, poster_url, poster_path)
            framed_path = config.framed_posters_dir / f"{kp_id}.jpg"
            if config.framed_force_regenerate or not framed_path.exists():
                render_framed_poster(source_for_frame, framed_path, seed_key=kp_id)
            image_url = f"{config.framed_posters_base_url}/{kp_id}.jpg"

        description = _build_seo_description(
            title=movie_title, genre=primary_genre, year=year,
            rating=rating, bot_url=config.bot_url, i=i,
        )

        keywords = _build_keywords(
            "фильмы", "кино", "что посмотреть",
            primary_genre, movie_title, year if year else None,
        )

        pins.append({
            "id": kp_id,
            "image_url": image_url,
            "poster_url": poster_url,
            "title": seo_title,
            "original_title": original_title,
            "year": year,
            "rating": rating,
            "genres": genres,
            "primary_genre": primary_genre,
            "kp_url": kp_url,
            "source_type": "poster",
            "description": description,
            "keywords": keywords,
            "category": "Фильмы",
            "board": board,
            "board_id": config.pinterest_board_id,
            "status": "pending",
            "created_at": now_str,
            "posted_at": "",
            "notes": "",
            "public_image_url": "",
            "remote_image_path": "",
            "vds_upload_status": "pending",
            "uploaded_at": "",
            "publish_status": "pending",
            "published_at": "",
            "error_reason": "",
        })

    return pins, skip


def export_movie_pins_csv(
    input_csv: Path,
    output_csv: Optional[Path] = None,
    limit: Optional[int] = None,
    posters_dir: Optional[Path] = None,
) -> Path:
    """Export individual movie posters as Pinterest pins CSV."""
    if output_csv is None:
        output_csv = config.cache_dir / "pins.csv"

    pins, skip = build_movie_pin_rows(input_csv=input_csv, limit=limit, posters_dir=posters_dir)
    write_csv_dict(output_csv, pins, _MOVIE_PIN_FIELDNAMES, config.csv_delimiter, config.csv_encoding)
    if pins:
        sync_pin_rows(pins)

    skipped_total = sum(skip.values())
    console.print(
        f"[green]Exported {len(pins)} pins[/green] "
        f"([yellow]{skipped_total} skipped: "
        f"{skip['invalid']} invalid, "
        f"{skip['missing_poster']} missing poster, "
        f"{skip['duplicate']} duplicates[/yellow])"
    )
    return output_csv