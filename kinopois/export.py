"""Export functionality for collages and metadata."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from rich.console import Console

from kinopois.config import config
from kinopois.database import Database

console = Console()

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

            films_list = ", ".join([collage.film1, collage.film2, collage.film3, collage.film4])

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

    with open(output_path, "w", newline="", encoding=config.csv_encoding) as f:
        # Header for n8n → Pinterest
        f.write("image_url;title;description;board;genre\n")

        for i, collage in enumerate(collages):
            if i >= len(TITLE_TEMPLATES):
                break

            title = TITLE_TEMPLATES[i]
            filename = collage.collage_file
            image_url = f"{config.base_image_url}/{filename}"

            films_list = ", ".join([collage.film1, collage.film2, collage.film3, collage.film4])

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
            board_map = {
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
            board = board_map.get(collage.genre.lower(), "Фильмы")

            f.write(f'{image_url};"{title}";"{description}";{board};{collage.genre}\n')

    console.print(f"[green]Exported {min(len(collages), len(TITLE_TEMPLATES))} pins to {output_path}[/green]")
    return output_path
