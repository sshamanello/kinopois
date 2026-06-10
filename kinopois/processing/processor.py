"""Data processing for movies and collages."""

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from kinopois.config import config
from kinopois.publishing.db import sync_movies_clean_rows
from kinopois.utils import get_primary_genre, parse_rating, read_csv_dict, safe_filename, write_csv_dict
from kinopois.logging_setup import get_logger
logger = get_logger(__name__)

console = Console()


class MovieProcessor:
    """Process movie data from CSV files."""

    def __init__(self, input_csv: Path):
        """Initialize processor with input CSV path."""
        self.input_csv = input_csv
        self.movies: List[Dict[str, Any]] = []

    def load(self) -> None:
        """Load movies from CSV file."""
        self.movies = read_csv_dict(
            self.input_csv,
            delimiter=config.csv_delimiter,
            encoding=config.csv_encoding,
        )
        console.print(f"[green]Loaded {len(self.movies)} movies from {self.input_csv}[/green]")

    def clean(self, output_csv: Optional[Path] = None) -> Path:
        """Clean movie data: filter valid entries and add primary_genre.

        Returns:
            Path to output CSV file.
        """
        if output_csv is None:
            output_csv = config.cache_dir / "movies_clean.csv"

        cleaned = []
        for movie in self.movies:
            poster_file = movie.get("poster_file", "").strip()
            genres = movie.get("genres", "").strip()
            title = movie.get("title", "").strip()

            # Skip movies without poster or genres
            if not poster_file or not genres:
                continue

            # Normalize path separators (CSV may contain Windows-style backslashes)
            poster_file = poster_file.replace("\\", "/")
            movie["poster_file"] = poster_file

            # Check if poster file exists
            if not Path(poster_file).exists():
                continue

            movie["primary_genre"] = get_primary_genre(genres)
            cleaned.append(movie)

            console.print(f"[cyan]Kept:[/cyan] {title} [{movie['primary_genre']}]")

        # Build fieldnames from cleaned rows because the first source row may be skipped
        # and not contain "primary_genre".
        if cleaned:
            fieldnames = list(cleaned[0].keys())
        elif self.movies:
            fieldnames = list(self.movies[0].keys())
        else:
            fieldnames = []
        write_csv_dict(output_csv, cleaned, fieldnames, config.csv_delimiter, config.csv_encoding)
        if cleaned:
            sync_movies_clean_rows(cleaned)

        console.print(f"[green]Cleaned data saved to {output_csv} ({len(cleaned)} movies)[/green]")
        return output_csv

    def group_by_genre(self) -> Dict[str, List[Dict[str, Any]]]:
        """Group movies by primary genre and sort by rating.

        Returns:
            Dictionary mapping genre to list of movies.
        """
        groups = defaultdict(list)

        for movie in self.movies:
            genre = movie.get("primary_genre", "").strip()
            poster_file = movie.get("poster_file", "").strip()

            if not genre or not poster_file:
                continue

            if not Path(poster_file).exists():
                continue

            rating = parse_rating(movie.get("rating_kp", ""))

            groups[genre].append({
                "title": movie.get("title", ""),
                "poster_file": poster_file,
                "rating": rating,
            })

        # Sort each group by rating (descending)
        for genre in groups:
            groups[genre] = sorted(groups[genre], key=lambda m: -m["rating"])

        console.print(f"[green]Grouped into {len(groups)} genres[/green]")
        for genre, movies in groups.items():
            console.print(f"  [cyan]{genre}:[/cyan] {len(movies)} movies")

        return groups


def load_movies(input_csv: Optional[Path] = None) -> MovieProcessor:
    """Load movies from CSV and return processor.

    Args:
        input_csv: Path to CSV file. Defaults to cache_dir/movies.csv.

    Returns:
        MovieProcessor instance with loaded movies.
    """
    if input_csv is None:
        input_csv = config.cache_dir / "movies.csv"

    processor = MovieProcessor(input_csv)
    processor.load()
    return processor


def load_clean_movies(input_csv: Optional[Path] = None) -> MovieProcessor:
    """Load cleaned movies from CSV and return processor.

    Args:
        input_csv: Path to cleaned CSV file. Defaults to cache_dir/movies_clean.csv.

    Returns:
        MovieProcessor instance with loaded movies.
    """
    if input_csv is None:
        input_csv = config.cache_dir / "movies_clean.csv"

    processor = MovieProcessor(input_csv)
    processor.load()
    return processor
