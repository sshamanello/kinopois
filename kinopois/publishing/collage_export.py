"""Export collage metadata to CSV files.

This module handles the older collage-based pipeline (2x2 poster grids),
separate from the individual movie-pin pipeline in movie_pins.py.
"""

from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from kinopois.config import config
from kinopois.utils import read_csv_dict, write_csv_dict

console = Console()


# ── Pinterest title templates for collages ────────────────────────────────────

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


# ── Export functions ──────────────────────────────────────────────────────────


def export_pinterest_csv(
    input_csv: Path,
    output_csv: Optional[Path] = None,
    base_url: Optional[str] = None,
    bot_url: Optional[str] = None,
) -> Path:
    """Export collages to Pinterest-style CSV format."""
    if output_csv is None:
        output_csv = config.cache_dir / "pins.csv"

    base_url = base_url or config.base_image_url
    bot_url = bot_url or config.bot_url

    collages = read_csv_dict(input_csv, config.csv_delimiter, config.csv_encoding)
    if not collages:
        console.print("[yellow]No collages found in CSV[/yellow]")
        return output_csv

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

    fieldnames = [
        "id", "image_url", "title", "description", "keywords",
        "category", "board", "board_id", "status",
        "created_at", "posted_at", "notes",
    ]
    write_csv_dict(output_csv, pins, fieldnames, config.csv_delimiter, config.csv_encoding)
    console.print(f"[green]Exported {len(pins)} pins to {output_csv}[/green]")
    return output_csv


def export_simple_collages_csv(
    input_csv: Path,
    output_csv: Optional[Path] = None,
    bot_url: Optional[str] = None,
) -> Path:
    """Export collages to simple CSV format (genre, file, link)."""
    if output_csv is None:
        output_csv = config.cache_dir / "collages_export.csv"

    bot_url = bot_url or config.bot_url
    collages = read_csv_dict(input_csv, config.csv_delimiter, config.csv_encoding)

    exported = []
    for collage in collages:
        exported.append({
            "genre": collage.get("genre", ""),
            "collage_file": collage.get("collage_file", ""),
            "link": bot_url,
        })

    fieldnames = ["genre", "collage_file", "link"]
    write_csv_dict(output_csv, exported, fieldnames, config.csv_delimiter, config.csv_encoding)
    console.print(f"[green]Exported {len(exported)} collages to {output_csv}[/green]")
    return output_csv


def export_summary(
    collages_csv: Path,
    movies_csv: Path,
    output_path: Optional[Path] = None,
) -> Path:
    """Export a summary text file with statistics."""
    if output_path is None:
        output_path = config.cache_dir / "summary.txt"

    collages = read_csv_dict(collages_csv, config.csv_delimiter, config.csv_encoding)
    movies = read_csv_dict(movies_csv, config.csv_delimiter, config.csv_encoding)

    genre_counts = {}
    for collage in collages:
        genre = collage.get("genre", "unknown")
        genre_counts[genre] = genre_counts.get(genre, 0) + 1

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
    lines.extend(["", f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"])

    output_path.write_text("\n".join(lines), encoding="utf-8")
    console.print(f"[green]Summary saved to {output_path}[/green]")
    return output_path