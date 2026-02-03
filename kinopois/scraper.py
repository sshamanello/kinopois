"""Scraper for Kinopoisk API."""

import json
import random
import ssl
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import certifi
import requests
from requests.adapters import HTTPAdapter
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from urllib3.util.ssl_ import create_urllib3_context

from kinopois.config import config
from kinopois.database import Database, Movie
from kinopois.logger import get_logger

console = Console()
logger = get_logger()


class RateLimiter:
    """Rate limiter for API requests."""

    def __init__(
        self,
        requests_per_second: float = 3.0,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_multiplier: float = 2.0,
    ):
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second.
            max_retries: Maximum retry attempts.
            initial_delay: Initial delay between retries in seconds.
            max_delay: Maximum delay between retries in seconds.
            backoff_multiplier: Multiplier for exponential backoff.
        """
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.backoff_multiplier = backoff_multiplier
        self.last_request_time = 0

    def acquire(self):
        """Wait if necessary to maintain rate limit."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time

        if time_since_last < self.min_interval:
            sleep_time = self.min_interval - time_since_last
            time.sleep(sleep_time)

        self.last_request_time = time.time()

    def wait_with_backoff(self, attempt: int) -> float:
        """Calculate wait time with exponential backoff.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns:
            Wait time in seconds.
        """
        delay = min(
            self.initial_delay * (self.backoff_multiplier ** attempt),
            self.max_delay
        )
        time.sleep(delay)
        return delay


class KinopoiskScraper:
    """Scraper for Kinopoisk.dev API."""

    API_URL = "https://api.kinopoisk.dev/v1.4/movie"
    PROGRESS_FILE = "progress.json"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize scraper with API key.

        Args:
            api_key: Kinopoisk API key. If None, uses config.kinopoisk_api_key.
        """
        self.api_key = api_key or config.kinopoisk_api_key
        if not self.api_key:
            raise ValueError("Kinopoisk API key is required. Set KINOPOISK_API_KEY env var.")

        self.headers = {
            "X-API-KEY": self.api_key,
            "accept": "application/json",
        }

        # Create session with proper SSL verification
        self.session = requests.Session()

        # Use certifi certificate bundle for proper SSL verification
        self.session.verify = certifi.where()

        # Mount custom adapter for legacy server support if needed
        try:
            self.session.mount('https://', SSLAdapter())
        except Exception as e:
            logger.warning(f"Could not mount SSL adapter: {e}")

        # Initialize rate limiter from config
        self.rate_limiter = RateLimiter(
            requests_per_second=config.rate_limit_requests_per_second,
            max_retries=config.rate_limit_retry_attempts,
            initial_delay=config.rate_limit_initial_delay,
            max_delay=config.rate_limit_max_delay,
            backoff_multiplier=config.rate_limit_backoff_multiplier,
        )

        # Load progress tracking
        self.progress_file = config.data_dir / self.PROGRESS_FILE
        self.progress = self._load_progress()

    def _load_progress(self) -> Dict[str, Any]:
        """Load progress from file.

        Returns:
            Progress dictionary.
        """
        if self.progress_file.exists():
            try:
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading progress file: {e}")
                return {}
        return {}

    def _save_progress(self):
        """Save progress to file."""
        try:
            self.progress_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.progress_file, "w", encoding="utf-8") as f:
                json.dump(self.progress, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error saving progress file: {e}")

    def _update_progress(self, key: str, value: Any):
        """Update progress value.

        Args:
            key: Progress key.
            value: Progress value.
        """
        self.progress[key] = value
        self._save_progress()

    def fetch_movies(
        self,
        page: int = 1,
        limit: int = 50,
        rating_min: float = 6.0,
        rating_max: float = 10.0,
        year_min: int = 2000,
        year_max: int = 2025,
    ) -> tuple[List[Dict[str, Any]], int]:
        """Fetch movies from API with rate limiting and retry logic.

        Args:
            page: Page number.
            limit: Number of movies per page.
            rating_min: Minimum rating.
            rating_max: Maximum rating.
            year_min: Minimum year.
            year_max: Maximum year.

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

        # Rate limiting
        self.rate_limiter.acquire()

        for attempt in range(self.rate_limiter.max_retries):
            try:
                response = self.session.get(
                    self.API_URL,
                    headers=self.headers,
                    params=params,
                    timeout=30,
                )
                response.raise_for_status()
                data = response.json()

                logger.debug(f"Fetched page {page}: {len(data.get('docs', []))} movies")

                return data.get("docs", []), data.get("pages", 1)

            except requests.exceptions.SSLError as e:
                logger.log_ssl_error(self.API_URL, e)
                if attempt < self.rate_limiter.max_retries - 1:
                    wait_time = self.rate_limiter.wait_with_backoff(attempt)
                    console.print(f"[yellow]SSL Error, retrying in {wait_time:.1f}s... (attempt {attempt + 1}/{self.rate_limiter.max_retries})[/yellow]")
                    continue
                console.print(f"[red]SSL Error fetching movies: {e}[/red]")
                return [], 0

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response is not None else None
                logger.log_api_error(self.API_URL, status_code, str(e))

                if attempt < self.rate_limiter.max_retries - 1:
                    wait_time = self.rate_limiter.wait_with_backoff(attempt)
                    console.print(f"[yellow]HTTP {status_code}, retrying in {wait_time:.1f}s... (attempt {attempt + 1}/{self.rate_limiter.max_retries})[/yellow]")
                    continue

                console.print(f"[red]HTTP Error {status_code}: {e}[/red]")
                return [], 0

            except requests.RequestException as e:
                logger.error(f"Request error: {e}")
                if attempt < self.rate_limiter.max_retries - 1:
                    wait_time = self.rate_limiter.wait_with_backoff(attempt)
                    console.print(f"[yellow]Connection error, retrying in {wait_time:.1f}s... (attempt {attempt + 1}/{self.rate_limiter.max_retries})[/yellow]")
                    continue

                console.print(f"[red]Error fetching movies: {e}[/red]")
                return [], 0

        return [], 0

    def download_poster(self, url: str, filename: str) -> Optional[Path]:
        """Download poster image to posters directory with retry logic.

        Args:
            url: Poster URL.
            filename: Filename to save.

        Returns:
            Path to downloaded file or None if failed.
        """
        for attempt in range(self.rate_limiter.max_retries):
            try:
                # Rate limiting for downloads
                self.rate_limiter.acquire()

                response = self.session.get(url, stream=True, timeout=30)
                response.raise_for_status()

                filepath = config.posters_dir / filename
                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)

                logger.debug(f"Downloaded poster: {filename}")
                return filepath

            except requests.RequestException as e:
                if attempt < self.rate_limiter.max_retries - 1:
                    self.rate_limiter.wait_with_backoff(attempt)
                    continue

                logger.error(f"Error downloading poster from {url}: {e}")
                console.print(f"[red]Error downloading poster from {url}: {e}[/red]")
                return None

    def extract_movie_data(self, movie: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant data from movie API response.

        Args:
            movie: Movie data from API.

        Returns:
            Extracted movie data.
        """
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
        resume: bool = False,
    ) -> int:
        """Download movies with posters and save to database.

        Args:
            limit: Number of movies to download.
            resume: If True, resume from previous progress.

        Returns:
            Number of movies downloaded.
        """
        collected = 0
        page = 1
        movies_batch = []
        checked_pages = 0
        max_empty_pages = 5  # Stop after 5 consecutive pages with no new movies

        logger.log_operation("download", {"limit": limit, "resume": resume})

        with Database() as db:
            # Get existing movie IDs to avoid duplicates
            existing_ids = db.get_existing_kp_ids()
            console.print(f"[cyan]Found {len(existing_ids)} existing movies in database[/cyan]")

            # If resuming, get already processed count
            if resume and "last_page" in self.progress:
                page = self.progress["last_page"] + 1
                console.print(f"[cyan]Resuming from page {page}[/cyan]")

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                console=console,
            ) as progress_bar:
                task = progress_bar.add_task("[cyan]Downloading movies...", total=limit)

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

                        progress_bar.update(task, advance=1)
                        console.print(f"[green][{collected}/{limit}][/green] {data['title']} ({data['year']})")

                    # Save batch to database
                    if movies_batch:
                        db.add_movies_batch(movies_batch)
                        logger.increment_stat("movies_downloaded", len(movies_batch))
                        movies_batch.clear()

                        # Update progress
                        self._update_progress("last_page", page)
                        self._update_progress("downloaded_count", collected)
                        self._update_progress("last_update", time.time())

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

        logger.info(f"Download complete. Total movies: {collected}")
        console.print(f"[green]Downloaded {collected} movies to database[/green]")

        # Clear progress on successful completion
        if collected >= limit:
            self.progress.clear()
            self._save_progress()

        return collected


class SSLAdapter(HTTPAdapter):
    """Custom adapter that uses legacy SSL for compatibility with older servers."""

    def init_poolmanager(self, *args, **kwargs):
        """Initialize pool manager with legacy SSL support."""
        ctx = create_urllib3_context()
        # OP_LEGACY_SERVER_CONNECT allows connecting to legacy servers
        # This is needed for some older API endpoints
        ctx.options |= 0x4  # OP_LEGACY_SERVER_CONNECT
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)
