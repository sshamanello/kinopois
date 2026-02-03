"""Scraper for Kinopoisk API."""

import random
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from requests.adapters import HTTPAdapter
from rich.console import Console
from urllib3.util.ssl_ import create_urllib3_context

from kinopois.config import config
from kinopois.database import Database, Movie

# Disable SSL warnings
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

console = Console()


class SSLAdapter(HTTPAdapter):
    """Custom adapter that uses legacy SSL for compatibility."""

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)


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

        # Create session with custom SSL adapter
        self.session = requests.Session()
        self.session.mount('https://', SSLAdapter())
        self.session.verify = False

    def fetch_movies(
        self,
        page: int = 1,
        limit: int = 50,
        rating_min: float = 6.0,
        rating_max: float = 10.0,
        year_min: int = 2000,
        year_max: int = 2025,
        retries: int = 3,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Fetch movies from API.

        Returns:
            Tuple of (movies list, total pages)
        """
        # Random sort order to get different movies each time
        sort_options = [
            "rating.kp",
            "year",
            "votes.kp",
            "random"
        ]
        sort_field = random.choice(sort_options)

        params = {
            "page": page,
            "limit": limit,
            "rating.kp": f"{rating_min}-{rating_max}",
            "year": f"{year_min}-{year_max}",
            "sortField": sort_field,
            "sortType": random.choice([-1, 1]),  # Random ascending/descending
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

        for attempt in range(retries):
            try:
                response = self.session.get(
                    self.API_URL,
                    headers=self.headers,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("docs", []), data.get("pages", 1)
            except requests.RequestException as e:
                if attempt < retries - 1:
                    console.print(f"[yellow]Retrying... (attempt {attempt + 1}/{retries})[/yellow]")
                    time.sleep(2)
                    continue
                console.print(f"[red]Error fetching movies: {e}[/red]")
                return [], 0

    def download_poster(self, url: str, filename: str, retries: int = 3) -> Optional[Path]:
        """Download poster image to posters directory.

        Returns:
            Path to downloaded file or None if failed.
        """
        for attempt in range(retries):
            try:
                response = self.session.get(url, stream=True, timeout=30)
                response.raise_for_status()

                filepath = config.posters_dir / filename
                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return filepath
            except requests.RequestException as e:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                console.print(f"[red]Error downloading poster from {url}: {e}[/red]")
                return None

    def extract_movie_data(self, movie: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant data from movie API response."""
        kp_id = movie.get("id")
        title = movie.get("name") or ""
        original_title = movie.get("alternativeName") or movie.get("enName") or ""
        year = movie.get("year") or 0

        # Rating
        rating = 0.0
        if isinstance(movie.get("rating"), dict):
            rating = movie["rating"].get("kp") or 0.0

        # Genres
        genres_list = movie.get("genres") or []
        genres = ", ".join(g.get("name", "") for g in genres_list if g.get("name"))

        # Primary genre (first one)
        primary_genre = genres_list[0].get("name", "") if genres_list else ""

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
            "primary_genre": primary_genre,
            "rating_kp": rating,
            "poster_url": poster_full_url,
            "poster_preview_url": poster_url,
        }

    def download_and_save(
        self,
        limit: int = 200,
    ) -> int:
        """Download movies with posters and save to database.

        Returns:
            Number of movies downloaded.
        """
        collected = 0
        page = 1
        movies_batch = []
        checked_pages = 0
        max_empty_pages = 5  # Stop after 5 consecutive pages with no new movies

        with Database() as db:
            # Get existing movie IDs to avoid duplicates
            existing_ids = db.get_existing_kp_ids()
            console.print(f"[cyan]Found {len(existing_ids)} existing movies in database[/cyan]")

            while collected < limit and checked_pages < max_empty_pages:
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

                page_new_movies = 0
                for movie in movies:
                    if collected >= limit:
                        break

                    data = self.extract_movie_data(movie)
                    kp_id = data["kp_id"]

                    # Skip if already downloaded
                    if kp_id in existing_ids:
                        continue

                    # Check if movie has poster URL
                    poster_data = movie.get("poster", {})
                    poster_url = poster_data.get("url") or poster_data.get("previewUrl")

                    if not poster_url:
                        continue  # Skip movies without poster

                    # Download poster
                    poster_filename = f"{kp_id}.jpg"
                    poster_path = self.download_poster(poster_url, poster_filename)

                    if not poster_path:
                        console.print(f"[yellow]Failed to download poster for {data['title']}[/yellow]")
                        continue

                    # Create Movie object
                    movie_obj = Movie(
                        kp_id=kp_id,
                        title=data["title"],
                        original_title=data["original_title"],
                        year=data["year"],
                        genres=data["genres"],
                        primary_genre=data["primary_genre"],
                        rating_kp=data["rating_kp"],
                        poster_url=data["poster_url"],
                        poster_file=str(poster_path),
                    )

                    movies_batch.append(movie_obj)
                    existing_ids.add(kp_id)  # Mark as downloaded
                    collected += 1
                    page_new_movies += 1
                    console.print(f"[green][{collected}/{limit}][/green] {data['title']} ({data['year']})")

                # Save batch to database
                if movies_batch:
                    db.add_movies_batch(movies_batch)
                    movies_batch.clear()

                # Check if we found any new movies on this page
                if page_new_movies == 0:
                    checked_pages += 1
                    console.print(f"[yellow]No new movies on page {page} (checked {checked_pages}/{max_empty_pages})[/yellow]")
                else:
                    checked_pages = 0  # Reset counter if we found new movies

                page += 1
                if page > total_pages:
                    console.print(f"[yellow]Reached last page ({total_pages})[/yellow]")
                    break

        console.print(f"[green]Downloaded {collected} movies to database[/green]")
        return collected
