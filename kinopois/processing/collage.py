"""Collage creation for movie posters."""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image, ImageDraw, ImageFont
from rich.console import Console

from kinopois.config import config
from kinopois.publishing.db import sync_collages_rows
from kinopois.processing.processor import load_clean_movies
from kinopois.utils import safe_filename, write_csv_dict
from kinopois.logging_setup import get_logger
logger = get_logger(__name__)

console = Console()


class CollageCreator:
    """Create 2x2 collages from movie posters."""

    def __init__(
        self,
        tile_width: int = 500,
        tile_height: int = 750,
        watermark_text: str = "",
        max_per_genre: Optional[int] = None,
    ):
        """Initialize collage creator.

        Args:
            tile_width: Width of each poster tile.
            tile_height: Height of each poster tile.
            watermark_text: Text to overlay on collages.
            max_per_genre: Maximum collages per genre (None = unlimited).
        """
        self.tile_width = tile_width
        self.tile_height = tile_height
        self.watermark_text = watermark_text
        self.max_per_genre = max_per_genre
        self.collage_width = tile_width * 2
        self.collage_height = tile_height * 2

    def create_collage(
        self,
        posters: List[str],
        output_path: Path,
    ) -> Path:
        """Create a 2x2 collage from 4 poster paths.

        Args:
            posters: List of 4 paths to poster images.
            output_path: Path to save the collage.

        Returns:
            Path to created collage.
        """
        if len(posters) != 4:
            raise ValueError(f"Expected 4 posters, got {len(posters)}")

        # Create new image
        collage = Image.new("RGB", (self.collage_width, self.collage_height))

        # Paste posters in 2x2 grid
        positions = [
            (0, 0),  # Top-left
            (self.tile_width, 0),  # Top-right
            (0, self.tile_height),  # Bottom-left
            (self.tile_width, self.tile_height),  # Bottom-right
        ]

        for poster_path, (x, y) in zip(posters, positions):
            try:
                img = Image.open(poster_path)
                img = img.resize((self.tile_width, self.tile_height), Image.Resampling.LANCZOS)
                collage.paste(img, (x, y))
            except Exception as e:
                console.print(f"[red]Error loading {poster_path}: {e}[/red]")
                raise

        # Add watermark if specified
        if self.watermark_text:
            self._add_watermark(collage)

        # Save
        output_path.parent.mkdir(parents=True, exist_ok=True)
        collage.save(output_path, "JPEG", quality=95)
        return output_path

    def _add_watermark(self, image: Image.Image) -> None:
        """Add watermark text to image."""
        draw = ImageDraw.Draw(image)

        # Try to load a font, fall back to default
        try:
            font = ImageFont.truetype("arial.ttf", 32)
        except Exception:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32)
            except Exception:
                font = ImageFont.load_default()

        # Get text size
        bbox = draw.textbbox((0, 0), self.watermark_text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Position at bottom center
        x = (self.collage_width - text_width) // 2
        y = self.collage_height - text_height - 20

        # Draw semi-transparent background
        padding = 10
        draw.rectangle(
            [
                x - padding,
                y - padding,
                x + text_width + padding,
                y + text_height + padding,
            ],
            fill=(0, 0, 0, 128),
        )

        # Draw text
        draw.text((x, y), self.watermark_text, font=font, fill=(255, 255, 255, 255))

    def create_from_movies(
        self,
        groups: Dict[str, List[Dict[str, Any]]],
        output_dir: Optional[Path] = None,
    ) -> List[Dict[str, Any]]:
        """Create collages from grouped movies.

        Args:
            groups: Dictionary mapping genre to list of movies.
            output_dir: Directory to save collages. Defaults to config.collages_dir.

        Returns:
            List of collage metadata dictionaries.
        """
        if output_dir is None:
            output_dir = config.collages_dir

        output_dir.mkdir(parents=True, exist_ok=True)
        collages = []

        for genre, movies in groups.items():
            if len(movies) < 4:
                console.print(f"[yellow]Skipping {genre}: only {len(movies)} movies[/yellow]")
                continue

            collage_index = 1
            for i in range(0, len(movies), 4):
                batch = movies[i : i + 4]
                if len(batch) < 4:
                    break

                if self.max_per_genre and collage_index > self.max_per_genre:
                    break

                # Create collage
                safe_genre = safe_filename(genre)
                filename = f"{safe_genre}_{collage_index:02d}.jpg"
                output_path = output_dir / filename

                try:
                    self.create_collage([m["poster_file"] for m in batch], output_path)

                    collages.append({
                        "genre": genre,
                        "collage_file": filename,
                        "film1": batch[0]["title"],
                        "film2": batch[1]["title"],
                        "film3": batch[2]["title"],
                        "film4": batch[3]["title"],
                    })

                    console.print(f"[green]Created:[/green] {filename}")
                    collage_index += 1

                except Exception as e:
                    console.print(f"[red]Error creating collage for {genre}: {e}[/red]")

        console.print(f"[green]Created {len(collages)} collages[/green]")
        return collages


def create_collages(
    input_csv: Optional[Path] = None,
    output_dir: Optional[Path] = None,
    output_csv: Optional[Path] = None,
    watermark: Optional[str] = None,
    max_per_genre: Optional[int] = None,
) -> Path:
    """Create collages from cleaned movie CSV.

    Args:
        input_csv: Path to movies_clean.csv.
        output_dir: Directory to save collages.
        output_csv: Path to save collages metadata CSV.
        watermark: Watermark text. Defaults to config.watermark_text.
        max_per_genre: Maximum collages per genre.

    Returns:
        Path to output CSV with collage metadata.
    """
    # Load movies
    processor = load_clean_movies(input_csv)
    groups = processor.group_by_genre()

    # Create collages
    creator = CollageCreator(
        tile_width=config.collage_tile_width,
        tile_height=config.collage_tile_height,
        watermark_text=watermark or config.watermark_text,
        max_per_genre=max_per_genre or config.collage_max_per_genre,
    )

    collages = creator.create_from_movies(groups, output_dir)

    # Save metadata
    if output_csv is None:
        output_csv = config.cache_dir / "collages.csv"

    if collages:
        fieldnames = ["genre", "collage_file", "film1", "film2", "film3", "film4"]
        write_csv_dict(output_csv, collages, fieldnames, config.csv_delimiter, config.csv_encoding)
        sync_collages_rows(collages)
        console.print(f"[green]Collage metadata saved to {output_csv}[/green]")

    return output_csv
