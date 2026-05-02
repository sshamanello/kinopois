"""Scraper for Kinopoisk API."""

import csv
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console
from rich.progress import track

from kinopois.config import config
from kinopois.utils import read_csv_dict

console = Console()


class KinopoiskScraper:
    """Scraper for Kinopoisk.dev API."""

    API_URL = "https://api.kinopoisk.dev/v1.4/movie"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize scraper with API key."""
        self.api_key = api_key or config.kinopoisk_api_key
        if not self.api_key:
            raise ValueError("Kinopoisk API key is required. Set KINOPOISK_API_KEY env var.")

        self.headers = {
            "X-API-KEY": self.api_key,
            "accept": "application/json",
        }

    def fetch_movies(
        self,
        page: int = 1,
        limit: int = 50,
        rating_min: float = 6.0,
        rating_max: float = 10.0,
        year_min: int = 2000,
        year_max: int = 2025,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Fetch movies from API.

        Returns:
            Tuple of (movies list, total pages)
        """
        params = {
            "page": page,
            "limit": limit,
            "rating.kp": f"{rating_min}-{rating_max}",
            "year": f"{year_min}-{year_max}",
            "selectFields": [
                "id",
                "name",
                "alternativeName",
                "enName",
                "year",
                "genres",
                "rating",
                "poster",
            ],
        }

        try:
            response = requests.get(
                self.API_URL,
                headers=self.headers,
                params=params,
                timeout=20,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("docs", []), data.get("pages", 1)
        except requests.RequestException as e:
            console.print(f"[red]Error fetching movies: {e}[/red]")
            return [], 0

    def download_poster(self, url: str, filename: str) -> Optional[Path]:
        """Download poster image to posters directory.

        Returns:
            Path to downloaded file or None if failed.
        """
        try:
            response = requests.get(url, stream=True, timeout=20)
            response.raise_for_status()

            filepath = config.posters_dir / filename
            with open(filepath, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            return filepath
        except requests.RequestException as e:
            console.print(f"[red]Error downloading poster from {url}: {e}[/red]")
            return None

    def extract_movie_data(self, movie: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant data from movie API response."""
        kp_id = movie.get("id")
        title = movie.get("name") or ""
        original_title = movie.get("alternativeName") or movie.get("enName") or ""
        year = movie.get("year") or ""

        # Rating
        rating = None
        if isinstance(movie.get("rating"), dict):
            rating = movie["rating"].get("kp")

        # Genres
        genres_list = movie.get("genres") or []
        genres = ", ".join(g.get("name", "") for g in genres_list if g.get("name"))

        # Poster
        poster_data = movie.get("poster") or {}
        poster_url = poster_data.get("previewUrl") or poster_data.get("url")
        poster_full_url = poster_data.get("url") or poster_url

        return {
            "kp_id": kp_id,
            "title": title,
            "original_title": original_title,
            "year": year,
            "genres": genres,
            "rating_kp": rating,
            "poster_url": poster_full_url,
            "poster_preview_url": poster_url,
        }

    def download_and_save(
        self,
        output_csv: Optional[Path] = None,
        limit: int = 200,
        append_mode: bool = False,
    ) -> Path:
        """Download movies with posters and save to CSV.

        Returns:
            Path to output CSV file.
        """
        if output_csv is None:
            output_csv = config.cache_dir / "movies.csv"

        collected = 0
        page = 1
        existing_ids: set[str] = set()
        output_csv.parent.mkdir(parents=True, exist_ok=True)

        if append_mode and output_csv.exists():
            for row in read_csv_dict(output_csv, config.csv_delimiter, config.csv_encoding):
                kp_id = str(row.get("kp_id", "")).strip()
                if kp_id:
                    existing_ids.add(kp_id)

        fieldnames = [
            "kp_id",
            "title",
            "original_title",
            "year",
            "genres",
            "rating_kp",
            "poster_url",
            "poster_file",
        ]

        mode = "a" if append_mode and output_csv.exists() else "w"
        with open(output_csv, mode, newline="", encoding=config.csv_encoding) as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=config.csv_delimiter)
            if mode == "w":
                writer.writeheader()

            while collected < limit:
                movies, total_pages = self.fetch_movies(
                    page=page,
                    limit=config.page_size,
                    rating_min=config.rating_min,
                    rating_max=config.rating_max,
                    year_min=config.year_min,
                    year_max=config.year_max,
                )

                if not movies:
                    break

                for movie in movies:
                    if collected >= limit:
                        break

                    data = self.extract_movie_data(movie)
                    poster_url = data.pop("poster_preview_url", "")
                    kp_id = str(data.get("kp_id", "")).strip()

                    if not kp_id:
                        continue
                    if append_mode and kp_id in existing_ids:
                        continue

                    # Skip if no poster
                    if not poster_url:
                        continue

                    # Download poster
                    poster_filename = f"{kp_id}.jpg"
                    poster_path = self.download_poster(poster_url, poster_filename)

                    if not poster_path:
                        continue

                    data["poster_file"] = str(poster_path)
                    writer.writerow(data)
                    if append_mode:
                        existing_ids.add(kp_id)

                    collected += 1
                    console.print(f"[green][{collected}/{limit}][/green] {data['title']} ({data['year']})")

                page += 1
                if page > total_pages:
                    break

        console.print(f"[green]Downloaded {collected} movies to {output_csv}[/green]")
        return output_csv
