"""File marking functionality for posters."""

from pathlib import Path
from typing import Literal, Optional

from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
from rich.progress import track

from kinopois.config import config
from kinopois.utils import read_csv_dict

console = Console()

PositionType = Literal["top", "bottom", "corner"]


class PosterMarker:
    """Add watermarks and metadata to poster images."""

    def __init__(
        self,
        text: str = "",
        position: PositionType = "bottom",
        font_size: int = 24,
        opacity: int = 180,
    ):
        """Initialize marker.

        Args:
            text: Watermark text to add.
            position: Position of watermark (top, bottom, corner).
            font_size: Font size for watermark text.
            opacity: Opacity of watermark background (0-255).
        """
        self.text = text
        self.position = position
        self.font_size = font_size
        self.opacity = opacity

    def mark_file(self, input_path: Path, output_path: Optional[Path] = None) -> Path:
        """Add watermark to a single image file.

        Args:
            input_path: Path to input image.
            output_path: Path to save marked image. Defaults to overwriting input.

        Returns:
            Path to marked image.
        """
        if output_path is None:
            output_path = input_path

        try:
            img = Image.open(input_path).convert("RGB")
            self._add_watermark(img)
            img.save(output_path, "JPEG", quality=95)
            return output_path
        except Exception as e:
            console.print(f"[red]Error marking {input_path}: {e}[/red]")
            raise

    def _add_watermark(self, image: Image.Image) -> None:
        """Add watermark to image."""
        if not self.text:
            return

        draw = ImageDraw.Draw(image)
        width, height = image.size

        # Load font
        font = self._load_font()

        # Get text size
        bbox = draw.textbbox((0, 0), self.text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]

        # Calculate position
        padding = 10
        if self.position == "bottom":
            x = (width - text_width) // 2
            y = height - text_height - padding * 2
        elif self.position == "top":
            x = (width - text_width) // 2
            y = padding
        else:  # corner (bottom-right)
            x = width - text_width - padding * 2
            y = height - text_height - padding * 2

        # Draw background
        draw.rectangle(
            [
                x - padding,
                y - padding,
                x + text_width + padding,
                y + text_height + padding,
            ],
            fill=(0, 0, 0, self.opacity),
        )

        # Draw text
        draw.text((x, y), self.text, font=font, fill=(255, 255, 255, 255))

    def _load_font(self) -> ImageFont.FreeTypeFont:
        """Load font for watermark."""
        font_paths = [
            "arial.ttf",
            "Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:\\Windows\\Fonts\\arial.ttf",
        ]

        for font_path in font_paths:
            try:
                return ImageFont.truetype(font_path, self.font_size)
            except Exception:
                continue

        return ImageFont.load_default()

    def mark_directory(
        self,
        input_dir: Path,
        output_dir: Optional[Path] = None,
        pattern: str = "*.jpg",
    ) -> int:
        """Mark all images in a directory.

        Args:
            input_dir: Directory containing images.
            output_dir: Directory to save marked images. Defaults to input_dir.
            pattern: Glob pattern for image files.

        Returns:
            Number of marked files.
        """
        input_dir = Path(input_dir)
        if output_dir is None:
            output_dir = input_dir
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)

        files = list(input_dir.glob(pattern))
        console.print(f"Found {len(files)} files to mark")

        for filepath in track(files, description="Marking files..."):
            output_path = output_dir / filepath.name
            self.mark_file(filepath, output_path)

        console.print(f"[green]Marked {len(files)} files[/green]")
        return len(files)

    def mark_from_csv(
        self,
        csv_path: Path,
        output_dir: Optional[Path] = None,
    ) -> int:
        """Mark images listed in CSV file.

        Args:
            csv_path: Path to CSV with poster_file column.
            output_dir: Directory to save marked images. Defaults to overwriting.

        Returns:
            Number of marked files.
        """
        rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
        console.print(f"Found {len(rows)} entries in CSV")

        marked = 0
        for row in track(rows, description="Marking from CSV..."):
            poster_file = row.get("poster_file", "")
            if not poster_file:
                continue

            input_path = Path(poster_file)
            if not input_path.exists():
                continue

            if output_dir:
                output_dir = Path(output_dir)
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / input_path.name
            else:
                output_path = input_path

            self.mark_file(input_path, output_path)
            marked += 1

        console.print(f"[green]Marked {marked} files[/green]")
        return marked


def mark_posters(
    input_dir: Path,
    text: Optional[str] = None,
    position: PositionType = "bottom",
    output_dir: Optional[Path] = None,
) -> int:
    """Mark all posters in a directory.

    Args:
        input_dir: Directory containing poster images.
        text: Watermark text. Defaults to config.watermark_text.
        position: Position of watermark.
        output_dir: Output directory. Defaults to input_dir.

    Returns:
        Number of marked files.
    """
    marker = PosterMarker(
        text=text or config.watermark_text,
        position=position,
    )
    return marker.mark_directory(input_dir, output_dir)
