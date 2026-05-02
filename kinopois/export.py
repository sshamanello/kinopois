"""Export functionality for collages and metadata."""

import csv
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console

from kinopois.config import config
from kinopois.frame import render_framed_poster
from kinopois.utils import read_csv_dict, safe_filename, write_csv_dict

console = Console()


# ---------------------------------------------------------------------------
# Helpers for individual movie pin export
# ---------------------------------------------------------------------------

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
        # Valid KP rating: 1.0-10.0. Reject vote counts (e.g. 46241) or
        # date serials that sometimes leak from the DB created_at field.
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


def _refresh_clean_poster(kp_id: str, poster_url: str, fallback_path: Path) -> Path:
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

MOVIE_DESC_TEMPLATES = [
    "«{title}» — {genre} с рейтингом {rating} на Кинопоиске. Подборки по настроению: {bot_url}",
    "{title} ({year}). Рейтинг КП: {rating}. Жанр: {genre}. Найди похожее: {bot_url}",
    "Один из лучших {genre} — «{title}». Рейтинг {rating}. Кино-бот в Telegram: {bot_url}",
    "Смотри сегодня: «{title}» ({year}), {genre}, рейтинг КП {rating}. {bot_url}",
    "«{title}» — это {genre}, который стоит посмотреть. Рейтинг {rating}. Больше подборок: {bot_url}",
    "{title} — отличный выбор на вечер. {genre}, рейтинг {rating}. Кино-бот: {bot_url}",
    "Рейтинг {rating} на Кинопоиске — «{title}». {genre} {year} года. Подборки: {bot_url}",
    "Ищешь хороший {genre}? «{title}» с рейтингом {rating} — то что нужно. {bot_url}",
    "«{title}» ({year}) — {genre} с рейтингом {rating}. Рекомендации по жанрам: {bot_url}",
    "{title}: {genre}, {year} год, рейтинг КП {rating}. Найди похожие фильмы: {bot_url}",
    "Топовый {genre} — «{title}», рейтинг {rating}. Больше кино по настроению: {bot_url}",
    "«{title}» {year} года. {genre}, рейтинг {rating}. Кино-бот подберёт ещё: {bot_url}",
    "{genre} «{title}» с рейтингом {rating}. Смотри и делись с друзьями. {bot_url}",
    "Рейтинг {rating} — «{title}» ({year}). Хороший {genre} на вечер. {bot_url}",
    "«{title}» — {genre} {year} года, рейтинг Кинопоиска {rating}. {bot_url}",
]

_MOVIE_PIN_FIELDNAMES = [
    "id", "image_url", "poster_url", "title", "original_title",
    "year", "rating", "genres", "primary_genre", "kp_url", "source_type",
    "description", "keywords", "category", "board", "board_id",
    "status", "created_at", "posted_at", "notes",
]


def export_movie_pins_csv(
    input_csv: Path,
    output_csv: Optional[Path] = None,
    limit: Optional[int] = None,
    posters_dir: Optional[Path] = None,
) -> Path:
    """Export individual movie posters as Pinterest pins CSV.

    Each movie in movies_clean.csv becomes one pin row.
    Rows with missing kp_id/title/genre or absent poster file are skipped.

    Args:
        input_csv: Path to movies_clean.csv.
        output_csv: Output path. Defaults to cache_dir/pins.csv.
        limit: Max valid pins to export (counts exported rows, not rows read).
        posters_dir: Override posters directory. Defaults to config.posters_dir.

    Returns:
        Path to written CSV.
    """
    if output_csv is None:
        output_csv = config.cache_dir / "pins.csv"

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
        title = _clean_str(row.get("title"))
        primary_genre = _normalize_genre(row.get("primary_genre") or row.get("genres"))

        if not _is_valid_pin_row(kp_id, title, primary_genre):
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
        poster_url = _clean_str(row.get("poster_url"))
        genres = _clean_str(row.get("genres"))
        board = GENRE_BOARD_MAP.get(primary_genre, "Фильмы")
        kp_url = f"https://www.kinopoisk.ru/film/{kp_id}/"
        image_url = f"{config.posters_base_url}/{kp_id}.jpg"
        if config.use_framed_posters:
            source_for_frame = _refresh_clean_poster(kp_id, poster_url, poster_path)
            framed_path = config.framed_posters_dir / f"{kp_id}.jpg"
            if not framed_path.exists():
                render_framed_poster(source_for_frame, framed_path, seed_key=kp_id)
            image_url = f"{config.framed_posters_base_url}/{kp_id}.jpg"

        tmpl = MOVIE_DESC_TEMPLATES[i % len(MOVIE_DESC_TEMPLATES)]
        description = tmpl.format(
            title=title,
            genre=primary_genre,
            rating=rating,
            year=year or "—",
            bot_url=config.bot_url,
        )

        keywords = _build_keywords(
            "фильмы", "кино", "что посмотреть",
            primary_genre, title,
            year if year else None,
        )

        pins.append({
            "id": kp_id,
            "image_url": image_url,
            "poster_url": poster_url,
            "title": title,
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
        })

    write_csv_dict(output_csv, pins, _MOVIE_PIN_FIELDNAMES, config.csv_delimiter, config.csv_encoding)

    skipped_total = sum(skip.values())
    console.print(
        f"[green]Exported {len(pins)} pins[/green] "
        f"([yellow]{skipped_total} skipped: "
        f"{skip['invalid']} invalid, "
        f"{skip['missing_poster']} missing poster, "
        f"{skip['duplicate']} duplicates[/yellow])"
    )
    return output_csv


# ---------------------------------------------------------------------------
# Pinterest-style titles templates (collage pipeline — unchanged)
# ---------------------------------------------------------------------------

# Pinterest-style titles templates
TITLE_TEMPLATES = [
    "4 мелодрамы, которые хочется смотреть запоем",
    "4 мелодрамы для уютного вечера вдвоём",
    "4 мелодрамы, оставляющие тёплое послевкусие",
    "4 мелодрамы, которые цепляют с первых минут",
    "4 мелодрамы, чтобы погрузиться в чувства по полной",
    "4 детектива, от которых невозможно оторваться",
    "4 комедии, чтобы поднять себе настроение",
    "4 комедии, которые реально смешные",
    "4 комедии на вечер, когда хочется просто расслабиться",
    "4 комедии, которые заставят улыбаться до конца",
    "4 триллера, которые держат в напряжении каждый кадр",
    "4 триллера, после которых сложно уснуть",
    "4 триллера с мощными сюжетными твистами",
    "4 триллера, которые пробирают до мурашек",
    "4 триллера для тех, кто любит настоящий саспенс",
    "4 драмы, которые бьют в самое сердце",
    "4 драмы, оставляющие долгий след в голове",
    "4 драмы, которые хочется обсуждать",
    "4 драмы, основанные на сильных историях",
    "4 драмы, которые заставляют задуматься",
    "4 эмоциональные драмы на вечер",
    "4 драмы, которые трогают до глубины души",
    "4 драмы, которые невозможно забыть",
    "4 драмы для тех, кто любит сильные переживания",
    "4 драмы, которые цепляют с первых минут",
    "4 мощные драмы, которые смотрятся на одном дыхании",
    "4 драмы, которые раскрывают человеческие истории",
    "4 глубокие драмы для вдумчивого просмотра",
    "4 документалки, которые реально расширяют кругозор",
    "4 документальных фильма, от которых сложно отвести взгляд",
    "4 документалки с сильным посылом",
    "4 документалки, которые нужно увидеть каждому",
    "4 документальных фильма, которые вдохновляют",
    "4 боевика, где действие начинается сразу",
    "4 боевика для заряда адреналином",
    "4 аниме, которые стоит посмотреть новичку",
    "4 аниме, которые цепляют с первой серии",
    "4 атмосферных аниме для вечера",
    "4 аниме, которые тебя удивят",
    "4 мультфильма для идеального семейного вечера",
    "4 мультфильма, которые создают уютное настроение",
]


def export_pinterest_csv(
    input_csv: Path,
    output_csv: Optional[Path] = None,
    base_url: Optional[str] = None,
    bot_url: Optional[str] = None,
) -> Path:
    """Export collages to Pinterest-style CSV format.

    Args:
        input_csv: Path to collages CSV with film1-4 columns.
        output_csv: Path to output CSV. Defaults to cache_dir/pins.csv.
        base_url: Base URL for images. Defaults to config.base_image_url.
        bot_url: Bot URL for descriptions. Defaults to config.bot_url.

    Returns:
        Path to output CSV.
    """
    if output_csv is None:
        output_csv = config.cache_dir / "pins.csv"

    base_url = base_url or config.base_image_url
    bot_url = bot_url or config.bot_url

    # Load collages
    collages = read_csv_dict(input_csv, config.csv_delimiter, config.csv_encoding)

    if not collages:
        console.print("[yellow]No collages found in CSV[/yellow]")
        return output_csv

    # Generate pins
    pins = []
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for i, collage in enumerate(collages):
        if i >= len(TITLE_TEMPLATES):
            break

        genre = collage.get("genre", "")
        collage_file = collage.get("collage_file", "")
        films = [collage.get(f"film{j}", "") for j in range(1, 5)]
        films_list = ", ".join([f for f in films if f])

        title = TITLE_TEMPLATES[i]
        filename = Path(collage_file).name
        image_url = f"{base_url}/{filename}"

        description = (
            f"{title}. Фильмы в подборке: {films_list}.\n"
            f"Напиши нашему кино-боту в Telegram, чтобы быстро найти фильмы под настроение: {bot_url}"
        )

        keywords = f"фильмы,{genre},подборка,что посмотреть,кино на вечер"

        pins.append({
            "id": i + 1,
            "image_url": image_url,
            "title": title,
            "description": description,
            "keywords": keywords,
            "category": "Фильмы",
            "board": "Фильмы на вечер",
            "board_id": config.pinterest_board_id,
            "status": "pending",
            "created_at": now_str,
            "posted_at": "",
            "notes": "",
        })

    # Write CSV
    fieldnames = [
        "id",
        "image_url",
        "title",
        "description",
        "keywords",
        "category",
        "board",
        "board_id",
        "status",
        "created_at",
        "posted_at",
        "notes",
    ]

    write_csv_dict(output_csv, pins, fieldnames, config.csv_delimiter, config.csv_encoding)

    console.print(f"[green]Exported {len(pins)} pins to {output_csv}[/green]")
    return output_csv


def export_simple_collages_csv(
    input_csv: Path,
    output_csv: Optional[Path] = None,
    bot_url: Optional[str] = None,
) -> Path:
    """Export collages to simple CSV format (genre, file, link).

    Args:
        input_csv: Path to collages CSV.
        output_csv: Path to output CSV. Defaults to cache_dir/collages_export.csv.
        bot_url: Bot URL for link column. Defaults to config.bot_url.

    Returns:
        Path to output CSV.
    """
    if output_csv is None:
        output_csv = config.cache_dir / "collages_export.csv"

    bot_url = bot_url or config.bot_url

    # Load and transform
    collages = read_csv_dict(input_csv, config.csv_delimiter, config.csv_encoding)

    exported = []
    for collage in collages:
        exported.append({
            "genre": collage.get("genre", ""),
            "collage_file": collage.get("collage_file", ""),
            "link": bot_url,
        })

    # Write CSV
    fieldnames = ["genre", "collage_file", "link"]
    write_csv_dict(output_csv, exported, fieldnames, config.csv_delimiter, config.csv_encoding)

    console.print(f"[green]Exported {len(exported)} collages to {output_csv}[/green]")
    return output_csv


def export_summary(
    collages_csv: Path,
    movies_csv: Path,
    output_path: Optional[Path] = None,
) -> Path:
    """Export a summary text file with statistics.

    Args:
        collages_csv: Path to collages CSV.
        movies_csv: Path to movies CSV.
        output_path: Path to output text file.

    Returns:
        Path to output file.
    """
    if output_path is None:
        output_path = config.cache_dir / "summary.txt"

    # Load data
    collages = read_csv_dict(collages_csv, config.csv_delimiter, config.csv_encoding)
    movies = read_csv_dict(movies_csv, config.csv_delimiter, config.csv_encoding)

    # Count by genre
    genre_counts = {}
    for collage in collages:
        genre = collage.get("genre", "unknown")
        genre_counts[genre] = genre_counts.get(genre, 0) + 1

    # Write summary
    lines = [
        "KINOPOIS SUMMARY",
        "=" * 50,
        f"Total movies: {len(movies)}",
        f"Total collages: {len(collages)}",
        "",
        "Collages by genre:",
    ]

    for genre, count in sorted(genre_counts.items()):
        lines.append(f"  {genre}: {count}")

    lines.extend([
        "",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Summary saved to {output_path}[/green]")

    return output_path
