"""SQLite database for kinopois data."""

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from kinopois.config import config

console = Console()


@dataclass
class Movie:
    """Movie data model."""

    kp_id: int
    title: str
    original_title: str
    year: int
    genres: str
    primary_genre: str
    rating_kp: float
    poster_url: str
    poster_file: str
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


@dataclass
class Collage:
    """Collage data model."""

    id: Optional[int]
    genre: str
    collage_file: str
    film1: str
    film2: str
    film3: str
    film4: str
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()


class Database:
    """SQLite database manager."""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize database.

        Args:
            db_path: Path to database file. Defaults to data/kinopois.db
        """
        if db_path is None:
            db_path = config.data_dir / "kinopois.db"

        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None

    def connect(self):
        """Create database connection."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def create_tables(self):
        """Create database tables."""
        cursor = self.conn.cursor()

        # Movies table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS movies (
                kp_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                original_title TEXT,
                year INTEGER,
                genres TEXT,
                primary_genre TEXT,
                rating_kp REAL,
                poster_url TEXT,
                poster_file TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Collages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS collages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                genre TEXT NOT NULL,
                collage_file TEXT NOT NULL,
                film1 TEXT NOT NULL,
                film2 TEXT NOT NULL,
                film3 TEXT NOT NULL,
                film4 TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_movies_primary_genre
            ON movies(primary_genre)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_collages_genre
            ON collages(genre)
        """)

        self.conn.commit()

    def add_movie(self, movie: Movie) -> bool:
        """Add or update movie in database.

        Returns:
            True if added/updated, False on error.
        """
        cursor = self.conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO movies
                (kp_id, title, original_title, year, genres, primary_genre,
                 rating_kp, poster_url, poster_file, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                movie.kp_id, movie.title, movie.original_title, movie.year,
                movie.genres, movie.primary_genre, movie.rating_kp,
                movie.poster_url, movie.poster_file, movie.created_at
            ))
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            console.print(f"[red]Error adding movie: {e}[/red]")
            return False

    def add_movies_batch(self, movies: List[Movie]) -> int:
        """Add multiple movies to database.

        Returns:
            Number of movies added.
        """
        cursor = self.conn.cursor()
        added = 0
        try:
            for movie in movies:
                cursor.execute("""
                    INSERT OR REPLACE INTO movies
                    (kp_id, title, original_title, year, genres, primary_genre,
                     rating_kp, poster_url, poster_file, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    movie.kp_id, movie.title, movie.original_title, movie.year,
                    movie.genres, movie.primary_genre, movie.rating_kp,
                    movie.poster_url, movie.poster_file, movie.created_at
                ))
                added += 1
            self.conn.commit()
        except sqlite3.Error as e:
            console.print(f"[red]Error adding movies: {e}[/red]")
        return added

    def get_movies(self, genre: Optional[str] = None) -> List[Movie]:
        """Get movies from database.

        Args:
            genre: Filter by primary_genre. None for all movies.

        Returns:
            List of movies.
        """
        cursor = self.conn.cursor()

        if genre:
            cursor.execute("""
                SELECT * FROM movies WHERE primary_genre = ?
                ORDER BY rating_kp DESC
            """, (genre,))
        else:
            cursor.execute("""
                SELECT * FROM movies ORDER BY rating_kp DESC
            """)

        movies = []
        for row in cursor.fetchall():
            movies.append(Movie(
                kp_id=row["kp_id"],
                title=row["title"],
                original_title=row["original_title"] or "",
                year=row["year"] or 0,
                genres=row["genres"] or "",
                primary_genre=row["primary_genre"] or "",
                rating_kp=row["rating_kp"] or 0.0,
                poster_url=row["poster_url"] or "",
                poster_file=row["poster_file"] or "",
                created_at=row["created_at"] or "",
            ))
        return movies

    def get_movies_by_genre(self) -> dict[str, List[Movie]]:
        """Get movies grouped by genre.

        Returns:
            Dictionary mapping genre to list of movies.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT * FROM movies
            WHERE primary_genre IS NOT NULL AND primary_genre != ''
            ORDER BY primary_genre, rating_kp DESC
        """)

        genres = {}
        for row in cursor.fetchall():
            movie = Movie(
                kp_id=row["kp_id"],
                title=row["title"],
                original_title=row["original_title"] or "",
                year=row["year"] or 0,
                genres=row["genres"] or "",
                primary_genre=row["primary_genre"] or "",
                rating_kp=row["rating_kp"] or 0.0,
                poster_url=row["poster_url"] or "",
                poster_file=row["poster_file"] or "",
                created_at=row["created_at"] or "",
            )

            if movie.primary_genre not in genres:
                genres[movie.primary_genre] = []
            genres[movie.primary_genre].append(movie)

        return genres

    def add_collage(self, collage: Collage) -> int:
        """Add collage to database.

        Returns:
            Collage ID.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO collages (genre, collage_file, film1, film2, film3, film4)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (collage.genre, collage.collage_file,
              collage.film1, collage.film2, collage.film3, collage.film4))
        self.conn.commit()
        return cursor.lastrowid

    def get_collages(self, genre: Optional[str] = None) -> List[Collage]:
        """Get collages from database.

        Args:
            genre: Filter by genre. None for all collages.

        Returns:
            List of collages.
        """
        cursor = self.conn.cursor()

        if genre:
            cursor.execute("""
                SELECT * FROM collages WHERE genre = ?
                ORDER BY genre, id
            """, (genre,))
        else:
            cursor.execute("""
                SELECT * FROM collages ORDER BY genre, id
            """)

        collages = []
        for row in cursor.fetchall():
            collages.append(Collage(
                id=row["id"],
                genre=row["genre"],
                collage_file=row["collage_file"],
                film1=row["film1"],
                film2=row["film2"],
                film3=row["film3"],
                film4=row["film4"],
                created_at=row["created_at"] or "",
            ))
        return collages

    def get_stats(self) -> dict:
        """Get database statistics.

        Returns:
            Dictionary with stats.
        """
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM movies")
        movies_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM collages")
        collages_count = cursor.fetchone()[0]

        cursor.execute("""
            SELECT primary_genre, COUNT(*) as count
            FROM movies
            GROUP BY primary_genre
            ORDER BY count DESC
        """)
        genre_counts = {row[0]: row[1] for row in cursor.fetchall()}

        return {
            "movies": movies_count,
            "collages": collages_count,
            "by_genre": genre_counts,
        }

    def delete_collages(self):
        """Delete all collages from database."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM collages")
        self.conn.commit()

    def delete_movies(self):
        """Delete all movies from database."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM movies")
        self.conn.commit()

    def movie_exists(self, kp_id: int) -> bool:
        """Check if movie exists in database.

        Args:
            kp_id: Kinopoisk movie ID.

        Returns:
            True if movie exists.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT 1 FROM movies WHERE kp_id = ?", (kp_id,))
        return cursor.fetchone() is not None

    def get_existing_kp_ids(self) -> set[int]:
        """Get set of all existing Kinopoisk IDs.

        Returns:
            Set of kp_id values.
        """
        cursor = self.conn.cursor()
        cursor.execute("SELECT kp_id FROM movies")
        return {row[0] for row in cursor.fetchall()}
