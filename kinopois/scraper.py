"""Scraper for Kinopoisk API."""

import csv
import fcntl
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlsplit

import requests
from rich.console import Console
from rich.progress import track

from kinopois.config import config
from kinopois.eventlog import log_event
from kinopois.utils import read_csv_dict

console = Console()


class KinopoiskScraper:
    """Scraper for Kinopoisk.dev API."""

    API_URL = "https://api.poiskkino.dev/v1.4/movie"

    def __init__(self, api_key: Optional[str] = None):
        """Initialize scraper with API key."""
        self.api_key = api_key or config.kinopoisk_api_key
        if not self.api_key:
            raise ValueError("Kinopoisk API key is required. Set KINOPOISK_API_KEY env var.")
        self.api_url = (config.kinopoisk_api_url or self.API_URL).strip()
        self.resolve_ips = [
            ip.strip()
            for ip in (config.kinopoisk_resolve_ips or "").split(",")
            if ip.strip()
        ]

        self.headers = {
            "X-API-KEY": self.api_key,
            "accept": "application/json",
        }

    def _effective_page_limit(self, requested_limit: int) -> int:
        """Return requested per-page limit (no hard clamp)."""
        return max(1, int(requested_limit))

    def _fetch_movies_via_resolve(self, params: Dict[str, Any]) -> tuple[List[Dict[str, Any]], int]:
        """Fallback request path that mirrors curl --resolve for TLS/DNS issues."""
        if not self.resolve_ips:
            return [], 0

        parsed = urlsplit(self.api_url)
        host = parsed.hostname or "api.poiskkino.dev"
        query = urlencode(params, doseq=True)
        full_url = f"{self.api_url}?{query}"

        for ip in self.resolve_ips:
            cmd = [
                "curl",
                "-sS",
                "--fail",
                "--max-time",
                "25",
                "--resolve",
                f"{host}:443:{ip}",
                "-H",
                f"X-API-KEY: {self.api_key}",
                "-H",
                "accept: application/json",
                full_url,
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode != 0:
                continue
            try:
                data = json.loads(proc.stdout or "{}")
            except json.JSONDecodeError:
                continue
            return data.get("docs", []), data.get("pages", 1)

        return [], 0

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

        last_error: Optional[Exception] = None
        for attempt in range(1, 4):
            try:
                response = requests.get(
                    self.api_url,
                    headers=self.headers,
                    params=params,
                    timeout=20,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("docs", []), data.get("pages", 1)
            except requests.RequestException as e:
                last_error = e
                # Network/TLS errors: attempt curl --resolve fallback with configured IP pool.
                fallback_docs, fallback_pages = self._fetch_movies_via_resolve(params)
                if fallback_docs:
                    console.print("[yellow]Primary API request failed, used --resolve fallback[/yellow]")
                    log_event(
                        "fetch_movies_fallback_resolve",
                        page=page,
                        limit=limit,
                        docs=len(fallback_docs),
                    )
                    return fallback_docs, fallback_pages
                if attempt < 3:
                    time.sleep(2 * attempt)
                    continue
                break

        console.print(f"[red]Error fetching movies: {last_error}[/red]")
        log_event("fetch_movies_failed", page=page, limit=limit, error=str(last_error))
        return [], 0

    def download_poster(self, url: str, filename: str) -> Optional[Path]:
        """Download poster image to posters directory.

        Returns:
            Path to downloaded file or None if failed.
        """
        for attempt in range(1, 4):
            try:
                response = requests.get(url, stream=True, timeout=20)
                response.raise_for_status()

                filepath = config.posters_dir / filename
                with open(filepath, "wb") as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return filepath
            except requests.RequestException as e:
                if attempt < 3:
                    time.sleep(attempt)
                    continue
                console.print(f"[red]Error downloading poster from {url}: {e}[/red]")
                log_event("poster_download_failed", url=url, filename=filename, error=str(e))
                return None
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
        append_mode: bool = True,
    ) -> Path:
        """Download movies with posters and save to CSV.

        Returns:
            Path to output CSV file.
        """
        if output_csv is None:
            output_csv = config.cache_dir / "movies.csv"
        log_event(
            "download_and_save_started",
            output_csv=str(output_csv),
            limit=limit,
            append_mode=append_mode,
        )

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
        backup_rows: List[Dict[str, Any]] = []
        if mode == "w" and output_csv.exists():
            backup_rows = read_csv_dict(output_csv, config.csv_delimiter, config.csv_encoding)

        lock_path = output_csv.with_suffix(output_csv.suffix + ".lock")
        with open(lock_path, "w", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            with open(output_csv, mode, newline="", encoding=config.csv_encoding) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=config.csv_delimiter)
                if mode == "w":
                    writer.writeheader()

                while collected < limit:
                    per_page = self._effective_page_limit(config.page_size)
                    movies, total_pages = self.fetch_movies(
                        page=page,
                        limit=per_page,
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
                        # Use full URL first, then preview as network fallback.
                        poster_url = str(data.get("poster_url") or "").strip()
                        poster_preview_url = str(data.get("poster_preview_url") or "").strip()
                        kp_id = str(data.get("kp_id", "")).strip()

                        if not kp_id:
                            continue
                        if kp_id in existing_ids:
                            continue

                        # Skip if no poster at all.
                        if not poster_url and not poster_preview_url:
                            continue

                        # Download poster with URL fallback.
                        poster_filename = f"{kp_id}.jpg"
                        poster_path = None
                        for candidate_url in [poster_url, poster_preview_url]:
                            if not candidate_url:
                                continue
                            poster_path = self.download_poster(candidate_url, poster_filename)
                            if poster_path:
                                break

                        if not poster_path:
                            continue

                        data.pop("poster_preview_url", None)
                        data["poster_file"] = str(poster_path)
                        writer.writerow(data)
                        existing_ids.add(kp_id)

                        collected += 1
                        console.print(f"[green][{collected}/{limit}][/green] {data['title']} ({data['year']})")

                    page += 1
                    if page > total_pages:
                        break

        if mode == "w" and collected == 0 and backup_rows:
            with open(output_csv, "w", newline="", encoding=config.csv_encoding) as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=config.csv_delimiter)
                writer.writeheader()
                for row in backup_rows:
                    writer.writerow({k: row.get(k, "") for k in fieldnames})
            console.print(
                "[yellow]No new movies fetched; restored previous movies.csv snapshot[/yellow]"
            )

        console.print(f"[green]Downloaded {collected} movies to {output_csv}[/green]")
        log_event("download_and_save_completed", output_csv=str(output_csv), collected=collected, limit=limit)
        return output_csv
