"""Export functionality for collages and metadata."""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from kinopois.config import config
from kinopois.database import Database
from kinopois.logger import get_logger

console = Console()
logger = get_logger()

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

# Pinterest board mapping
BOARD_MAP = {
    "драма": "Драмы",
    "комедия": "Комедии",
    "мелодрама": "Мелодрамы",
    "трилер": "Триллеры",
    "детектив": "Детективы",
    "боевик": "Боевики",
    "документальный": "Документальное кино",
    "мультфильм": "Мультфильмы",
    "аниме": "Аниме",
}


def generate_tags(genre: str) -> list[str]:
    """Generate tags for a collage based on genre.

    Args:
        genre: Primary genre.

    Returns:
        List of tags.
    """
    base_tags = ["фильмы", "подборка", "кино", "что посмотреть", "кино на вечер"]
    genre_tags = []

    genre_lower = genre.lower()
    if genre_lower in ["драма", "драмы"]:
        genre_tags = ["драма", "сильные драмы"]
    elif genre_lower in ["комедия", "комедии"]:
        genre_tags = ["комедия", "смешное кино"]
    elif genre_lower in ["мелодрама", "мелодрамы"]:
        genre_tags = ["мелодрама", "романтика"]
    elif genre_lower in ["триллер", "триллеры"]:
        genre_tags = ["триллер", "саспенс", "напряженные фильмы"]
    elif genre_lower in ["детектив", "детективы"]:
        genre_tags = ["детектив", "загадки"]
    elif genre_lower in ["боевик", "боевики"]:
        genre_tags = ["боевик", "экшн", "action"]
    elif genre_lower in ["документальный", "документальное кино"]:
        genre_tags = ["документальное кино", "документалки"]
    elif genre_lower in ["мультфильм", "мультфильмы"]:
        genre_tags = ["мультфильм", "анимация"]
    elif genre_lower in ["аниме"]:
        genre_tags = ["аниме", "японская анимация"]

    return base_tags + genre_tags


def export_for_pinterest(
    db: Database,
    output_path: Optional[Path] = None,
) -> Path:
    """Export collages from database to Pinterest CSV format.

    Args:
        db: Database instance.
        output_path: Path to output CSV. Defaults to data/pins.csv.

    Returns:
        Path to output CSV.
    """
    if output_path is None:
        output_path = config.data_dir / "pins.csv"

    collages = db.get_collages()

    if not collages:
        console.print("[yellow]No collages found in database[/yellow]")
        return output_path

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(output_path, "w", newline="", encoding=config.csv_encoding) as f:
        f.write("id;image_url;title;description;keywords;category;board;board_id;status;created_at;posted_at;notes\n")

        for i, collage in enumerate(collages):
            if i >= len(TITLE_TEMPLATES):
                break

            title = TITLE_TEMPLATES[i]
            filename = collage.collage_file
            image_url = f"{config.base_image_url}/{filename}"

            films_list = ", ".join(collage.get_films_list())

            description = (
                f"{title}. Фильмы в подборке: {films_list}.\n"
                f"Напиши нашему кино-боту в Telegram, чтобы быстро найти фильмы под настроение: {config.bot_url}"
            )

            keywords = f"фильмы,{collage.genre},подборка,что посмотреть,кино на вечер"

            f.write(
                f"{i + 1};{image_url};{title};\"{description}\";{keywords};Фильмы;"
                f"Фильмы на вечер;;pending;{now_str};;\n"
            )

    console.print(f"[green]Exported {len(collages)} pins to {output_path}[/green]")
    return output_path


def export_for_n8n(
    db: Database,
    output_path: Optional[Path] = None,
) -> Path:
    """Export collages to CSV format optimized for n8n → Pinterest automation.

    CSV columns:
    - image_url: Direct link to collage image
    - title: Hook title (e.g., "4 мелодрамы, которые хочется смотреть запоем")
    - description: Description with film names and bot CTA
    - board: Pinterest board name
    - genre: Film genre for categorization

    Args:
        db: Database instance.
        output_path: Path to output CSV. Defaults to data/pinterest_n8n.csv.

    Returns:
        Path to output CSV.
    """
    if output_path is None:
        output_path = config.data_dir / "pinterest_n8n.csv"

    collages = db.get_collages()

    if not collages:
        console.print("[yellow]No collages found in database[/yellow]")
        return output_path

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Exporting to CSV...", total=len(collages))

        with open(output_path, "w", newline="", encoding=config.csv_encoding) as f:
            # Header for n8n → Pinterest
            f.write("image_url;title;description;board;genre\n")

            for i, collage in enumerate(collages):
                if i >= len(TITLE_TEMPLATES):
                    break

                title = TITLE_TEMPLATES[i]
                filename = collage.collage_file
                image_url = f"{config.base_image_url}/{filename}"

                # Rich description for Pinterest
                description = (
                    f"{title}\n\n"
                    f"🎬 Фильмы в подборке:\n"
                    f"• {collage.film1}\n"
                    f"• {collage.film2}\n"
                    f"• {collage.film3}\n"
                    f"• {collage.film4}\n\n"
                    f"🤖 Хочешь больше подборок под настроение? Напиши нашему кино-боту в Telegram!\n"
                    f"{config.bot_url}"
                )

                # Pinterest board name based on genre
                board = BOARD_MAP.get(collage.genre.lower(), "Фильмы")

                f.write(f'{image_url};"{title}";"{description}";{board};{collage.genre}\n')
                progress.update(task, advance=1)

    logger.info(f"Exported {min(len(collages), len(TITLE_TEMPLATES))} pins to {output_path}")
    console.print(f"[green]Exported {min(len(collages), len(TITLE_TEMPLATES))} pins to {output_path}[/green]")
    return output_path


def export_for_n8n_json(
    db: Database,
    output_path: Optional[Path] = None,
) -> Path:
    """Export collages to JSON format for n8n automation.

    Each object contains:
    - id: Collage ID
    - image_url: Direct link to collage image
    - title: Hook title for Pinterest
    - description: Full description with films list and CTA
    - board: Pinterest board name
    - genre: Film genre
    - file_size: File size in bytes
    - width: Image width in pixels
    - height: Image height in pixels
    - films: List of film titles
    - color_palette: List of dominant colors (hex codes)
    - created_at: Creation timestamp
    - tags: List of tags for Pinterest

    Args:
        db: Database instance.
        output_path: Path to output JSON. Defaults to data/pinterest_n8n.json.

    Returns:
        Path to output JSON.
    """
    if output_path is None:
        output_path = config.data_dir / "pinterest_n8n.json"

    collages = db.get_collages()

    if not collages:
        console.print("[yellow]No collages found in database[/yellow]")
        return output_path

    result = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("[cyan]Exporting to JSON...", total=len(collages))

        for i, collage in enumerate(collages):
            # Get title from templates (cycle through if needed)
            title = TITLE_TEMPLATES[i % len(TITLE_TEMPLATES)]

            filename = collage.collage_file
            image_url = f"{config.base_image_url}/{filename}"

            # Rich description for Pinterest
            description = (
                f"{title}\n\n"
                f"🎬 Фильмы в подборке:\n"
                f"• {collage.film1}\n"
                f"• {collage.film2}\n"
                f"• {collage.film3}\n"
                f"• {collage.film4}\n\n"
                f"🤖 Хочешь больше подборок под настроение? Напиши нашему кино-боту в Telegram!\n"
                f"{config.bot_url}"
            )

            # Pinterest board name based on genre
            board = BOARD_MAP.get(collage.genre.lower(), "Фильмы")

            # Parse color palette
            color_palette = collage.get_color_palette() or []

            # Build output object
            obj = {
                "id": collage.id,
                "image_url": image_url,
                "title": title,
                "description": description,
                "board": board,
                "genre": collage.genre,
                "file_size": collage.file_size,
                "width": collage.width,
                "height": collage.height,
                "films": collage.get_films_list(),
                "color_palette": color_palette,
                "created_at": collage.created_at,
                "tags": generate_tags(collage.genre),
            }

            result.append(obj)
            progress.update(task, advance=1)

    # Write to JSON file
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    logger.info(f"Exported {len(result)} collages to {output_path}")
    console.print(f"[green]Exported {len(result)} collages to {output_path}[/green]")
    return output_path
