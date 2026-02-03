"""Collage creation for movie posters."""

import json
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from kinopois.config import config
from kinopois.database import Database, Collage
from kinopois.logger import get_logger
from kinopois.utils import safe_filename

console = Console()
logger = get_logger()


def extract_color_palette(image: Image.Image, num_colors: int = 5) -> List[str]:
    """Extract dominant colors from an image using k-means clustering.

    Args:
        image: PIL Image object.
        num_colors: Number of colors to extract.

    Returns:
        List of hex color codes.
    """
    # Convert to RGB if necessary
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Resize for faster processing
    small_image = image.resize((150, 150))

    # Get pixel data
    pixels = list(small_image.getdata())

    # Simple color quantization using frequency
    from collections import Counter
    color_counts = Counter(pixels)
    most_common = color_counts.most_common(num_colors * 10)  # Get more candidates

    # Convert to hex and return top colors
    palette = []
    for rgb, _ in most_common:
        if len(palette) >= num_colors:
            break
        hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
        palette.append(hex_color)

    return palette


def get_file_size(filepath: Path) -> int:
    """Get file size in bytes.

    Args:
        filepath: Path to file.

    Returns:
        File size in bytes.
    """
    return filepath.stat().st_size if filepath.exists() else 0


def format_file_size(size_bytes: int) -> str:
    """Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes.

    Returns:
        Formatted size string (e.g., "1.5 MB").
    """
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


class CollageCreator:
    """Create 2x2 collages from movie posters."""

    def __init__(
        self,
        tile_width: int = 500,
        tile_height: int = 750,
        watermark_text: str = "",
        max_per_genre: Optional[int] = None,
        extract_metadata: bool = True,
    ):
        """Initialize collage creator.

        Args:
            tile_width: Width of each poster tile.
            tile_height: Height of each poster tile.
            watermark_text: Text to overlay on collages.
            max_per_genre: Maximum collages per genre (None = unlimited).
            extract_metadata: Whether to extract metadata from created collages.
        """
        self.tile_width = tile_width
        self.tile_height = tile_height
        self.watermark_text = watermark_text
        self.max_per_genre = max_per_genre
        self.extract_metadata = extract_metadata
        self.collage_width = tile_width * 2
        self.collage_height = tile_height * 2

    def create_collage(
        self,
        posters: List[str],
        output_path: Path,
    ) -> Tuple[Path, dict]:
        """Create a 2x2 collage from 4 poster paths.

        Args:
            posters: List of 4 paths to poster images.
            output_path: Path to save the collage.

        Returns:
            Tuple of (path to created collage, metadata dict).

        Raises:
            ValueError: If not exactly 4 posters provided.
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

        # Extract metadata
        metadata = {
            "width": self.collage_width,
            "height": self.collage_height,
        }

        if self.extract_metadata:
            metadata["file_size"] = get_file_size(output_path)
            metadata["color_palette"] = extract_color_palette(collage)

        return output_path, metadata

    def _add_watermark(self, image: Image.Image) -> None:
        """Add watermark text to image.

        Args:
            image: PIL Image object.
        """
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


def create_collages(
    output_dir: Optional[Path] = None,
    watermark: Optional[str] = None,
    max_per_genre: Optional[int] = None,
    dry_run: bool = False,
) -> int:
    """Create collages from movies in database.

    Args:
        output_dir: Directory to save collages.
        watermark: Watermark text. Defaults to config.watermark_text.
        max_per_genre: Maximum collages per genre.
        dry_run: If True, simulate without creating files.

    Returns:
        Number of collages created (or would be created in dry-run mode).
    """
    if output_dir is None:
        output_dir = config.collages_dir

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.log_operation("collage", {"dry_run": dry_run, "max_per_genre": max_per_genre})

    # Create collage creator
    creator = CollageCreator(
        tile_width=config.collage_tile_width,
        tile_height=config.collage_tile_height,
        watermark_text=watermark or config.watermark_text,
        max_per_genre=max_per_genre or config.collage_max_per_genre,
        extract_metadata=not dry_run,
    )

    # Get movies grouped by genre from database
    with Database() as db:
        genre_groups = db.get_movies_by_genre()

        # Get existing collages to continue numbering
        existing_collages = db.get_collages()
        max_index_by_genre = {}
        for c in existing_collages:
            if c.genre not in max_index_by_genre:
                max_index_by_genre[c.genre] = 0
            # Extract number from filename like "драма_01.jpg"
            if "_" in c.collage_file:
                try:
                    num = int(c.collage_file.split("_")[-1].replace(".jpg", ""))
                    max_index_by_genre[c.genre] = max(max_index_by_genre[c.genre], num)
                except Exception:
                    pass

        # Count total potential collages
        total_potential = sum(
            len(movies) // 4
            for movies in genre_groups.values()
            if len(movies) >= 4
        )

        created_count = 0

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress_bar:
            task = progress_bar.add_task(
                "[cyan]Creating collages...",
                total=total_potential
            )

            for genre, movies in genre_groups.items():
                if len(movies) < 4:
                    progress_bar.console.print(f"[yellow]Skipping {genre}: only {len(movies)} movies[/yellow]")
                    continue

                # Start from next number after existing
                collage_index = max_index_by_genre.get(genre, 0) + 1
                for i in range(0, len(movies), 4):
                    batch = movies[i : i + 4]
                    if len(batch) < 4:
                        break

                    if creator.max_per_genre and collage_index > creator.max_per_genre:
                        break

                    # Create collage
                    safe_genre = safe_filename(genre)
                    filename = f"{safe_genre}_{collage_index:02d}.jpg"
                    output_path = output_dir / filename

                    if dry_run:
                        console.print(f"[yellow][DRY RUN] Would create:[/yellow] {filename}")
                        console.print(f"  Films: {', '.join(m.title for m in batch)}")

                        # Create metadata for dry-run
                        metadata = {
                            "width": creator.collage_width,
                            "height": creator.collage_height,
                            "file_size": 0,
                            "color_palette": [],
                        }
                    else:
                        try:
                            output_path, metadata = creator.create_collage(
                                [m.poster_file for m in batch],
                                output_path
                            )

                            console.print(
                                f"[green]Created:[/green] {filename} "
                                f"({metadata['width']}x{metadata['height']}, "
                                f"{format_file_size(metadata.get('file_size', 0))})"
                            )

                        except Exception as e:
                            logger.error(f"Error creating collage for {genre}: {e}")
                            console.print(f"[red]Error creating collage for {genre}: {e}[/red]")
                            continue

                    # Save to database
                    collage = Collage(
                        id=None,
                        genre=genre,
                        collage_file=filename,
                        film1=batch[0].title,
                        film2=batch[1].title,
                        film3=batch[2].title,
                        film4=batch[3].title,
                        width=metadata.get("width"),
                        height=metadata.get("height"),
                        file_size=metadata.get("file_size"),
                        color_palette=json.dumps(metadata.get("color_palette", [])) if metadata.get("color_palette") else None,
                    )

                    if not dry_run:
                        db.add_collage(collage)
                        logger.increment_stat("collages_created")

                    created_count += 1
                    collage_index += 1
                    progress_bar.update(task, advance=1)

    logger.info(f"Collage creation complete. Total: {created_count}")
    console.print(f"[green]{'[DRY RUN] Would create' if dry_run else 'Created'} {created_count} collages[/green]")
    return created_count
