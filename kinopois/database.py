"""SQLite database for kinopois data."""

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from rich.console import Console

from kinopois.config import config
from kinopois.logger import get_logger

console = Console()
logger = get_logger()


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
    width: Optional[int] = None
    height: Optional[int] = None
    file_size: Optional[int] = None
    color_palette: Optional[str] = None  # JSON string
    created_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()

    def get_films_list(self) -> List[str]:
        """Get list of film titles."""
        return [self.film1, self.film2, self.film3, self.film4]

    def get_color_palette(self) -> Optional[List[str]]:
        """Parse color palette from JSON string."""
        if self.color_palette:
            try:
                return json.loads(self.color_palette)
            except json.JSONDecodeError:
                pass
        return None


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

        # Check if collages table needs migration (add new columns)
        cursor.execute("PRAGMA table_info(collages)")
        columns_info = cursor.fetchall()
        existing_columns = {col[1] for col in columns_info}

        # Create collages table with new columns if it doesn't exist
        if not existing_columns:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS collages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    genre TEXT NOT NULL,
                    collage_file TEXT NOT NULL,
                    film1 TEXT NOT NULL,
                    film2 TEXT NOT NULL,
                    film3 TEXT NOT NULL,
                    film4 TEXT NOT NULL,
                    width INTEGER,
                    height INTEGER,
                    file_size INTEGER,
                    color_palette TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
        else:
            # Migrate: add new columns if they don't exist
            new_columns = {
                "width": "INTEGER",
                "height": "INTEGER",
                "file_size": "INTEGER",
                "color_palette": "TEXT",
            }

            for col_name, col_type in new_columns.items():
                if col_name not in existing_columns:
                    try:
                        cursor.execute(f"ALTER TABLE collages ADD COLUMN {col_name} {col_type}")
                        logger.info(f"Added column {col_name} to collages table")
                    except sqlite3.OperationalError as e:
                        logger.warning(f"Could not add column {col_name}: {e}")

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

        Args:
            movie: Movie object.

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
            logger.error(f"Error adding movie: {e}")
            return False

    def add_movies_batch(self, movies: List[Movie]) -> int:
        """Add multiple movies to database using executemany for efficiency.

        Args:
            movies: List of Movie objects.

        Returns:
            Number of movies added.
        """
        if not movies:
            return 0

        cursor = self.conn.cursor()
        added = 0

        try:
            # Begin transaction
            self.conn.execute("BEGIN TRANSACTION")

            # Prepare data for executemany
            movie_data = [
                (
                    m.kp_id, m.title, m.original_title, m.year,
                    m.genres, m.primary_genre, m.rating_kp,
                    m.poster_url, m.poster_file, m.created_at
                )
                for m in movies
            ]

            # Use executemany for efficient bulk insert
            cursor.executemany("""
                INSERT OR REPLACE INTO movies
                (kp_id, title, original_title, year, genres, primary_genre,
                 rating_kp, poster_url, poster_file, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, movie_data)

            added = len(movies)

            # Commit transaction
            self.conn.commit()
            logger.debug(f"Added {added} movies in batch")

        except sqlite3.Error as e:
            # Rollback on error
            self.conn.rollback()
            logger.error(f"Error adding movies batch, rolled back: {e}")

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

        Args:
            collage: Collage object.

        Returns:
            Collage ID.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO collages
            (genre, collage_file, film1, film2, film3, film4, width, height, file_size, color_palette)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            collage.genre, collage.collage_file,
            collage.film1, collage.film2, collage.film3, collage.film4,
            collage.width, collage.height, collage.file_size, collage.color_palette
        ))
        self.conn.commit()
        return cursor.lastrowid

    def add_collages_batch(self, collages: List[Collage]) -> int:
        """Add multiple collages to database using executemany.

        Args:
            collages: List of Collage objects.

        Returns:
            Number of collages added.
        """
        if not collages:
            return 0

        cursor = self.conn.cursor()
        added = 0

        try:
            # Begin transaction
            self.conn.execute("BEGIN TRANSACTION")

            # Prepare data for executemany
            collage_data = [
                (
                    c.genre, c.collage_file,
                    c.film1, c.film2, c.film3, c.film4,
                    c.width, c.height, c.file_size, c.color_palette
                )
                for c in collages
            ]

            # Use executemany for efficient bulk insert
            cursor.executemany("""
                INSERT INTO collages
                (genre, collage_file, film1, film2, film3, film4, width, height, file_size, color_palette)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, collage_data)

            added = len(collages)

            # Commit transaction
            self.conn.commit()
            logger.debug(f"Added {added} collages in batch")

        except sqlite3.Error as e:
            # Rollback on error
            self.conn.rollback()
            logger.error(f"Error adding collages batch, rolled back: {e}")

        return added

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
                width=row["width"],
                height=row["height"],
                file_size=row["file_size"],
                color_palette=row["color_palette"],
                created_at=row["created_at"] or "",
            ))
        return collages

    def update_collage_metadata(
        self,
        collage_id: int,
        width: Optional[int] = None,
        height: Optional[int] = None,
        file_size: Optional[int] = None,
        color_palette: Optional[List[str]] = None,
    ) -> bool:
        """Update metadata for a collage.

        Args:
            collage_id: Collage ID.
            width: Image width in pixels.
            height: Image height in pixels.
            file_size: File size in bytes.
            color_palette: List of color hex codes.

        Returns:
            True if updated successfully.
        """
        cursor = self.conn.cursor()

        # Build update query dynamically based on provided fields
        updates = []
        params = []

        if width is not None:
            updates.append("width = ?")
            params.append(width)

        if height is not None:
            updates.append("height = ?")
            params.append(height)

        if file_size is not None:
            updates.append("file_size = ?")
            params.append(file_size)

        if color_palette is not None:
            updates.append("color_palette = ?")
            params.append(json.dumps(color_palette))

        if not updates:
            return False

        params.append(collage_id)

        try:
            query = f"UPDATE collages SET {', '.join(updates)} WHERE id = ?"
            cursor.execute(query, params)
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error updating collage metadata: {e}")
            return False

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

        # Get total file sizes
        cursor.execute("SELECT SUM(file_size) FROM collages WHERE file_size IS NOT NULL")
        total_collages_size = cursor.fetchone()[0] or 0

        return {
            "movies": movies_count,
            "collages": collages_count,
            "by_genre": genre_counts,
            "total_collages_size_bytes": total_collages_size,
        }

    def delete_collages(self):
        """Delete all collages from database."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM collages")
        self.conn.commit()
        logger.info("Deleted all collages from database")

    def delete_movies(self):
        """Delete all movies from database."""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM movies")
        self.conn.commit()
        logger.info("Deleted all movies from database")

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

    def get_genres_with_counts(self) -> List[tuple[str, int]]:
        """Get list of genres with movie counts.

        Returns:
            List of (genre, count) tuples sorted by count descending.
        """
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT primary_genre, COUNT(*) as count
            FROM movies
            WHERE primary_genre IS NOT NULL AND primary_genre != ''
            GROUP BY primary_genre
            ORDER BY count DESC
        """)
        return [(row[0], row[1]) for row in cursor.fetchall()]

    def get_recommendations(self) -> List[str]:
        """Get recommendations based on database state.

        Returns:
            List of recommendation strings.
        """
        recommendations = []
        stats = self.get_stats()

        for genre, count in stats["by_genre"].items():
            if count < 20:
                recommendations.append(f"Download more {genre} movies (current: {count})")
            elif count >= 4 and count % 4 != 0:
                recommendations.append(f"Download {4 - (count % 4)} more {genre} movies for another collage")

        # Check for genres without collages
        genres_with_movies = set(stats["by_genre"].keys())
        collages = self.get_collages()
        genres_with_collages = {c.genre for c in collages}

        for genre in genres_with_movies - genres_with_collages:
            if stats["by_genre"][genre] >= 4:
                recommendations.append(f"Create collages for {genre} ({stats['by_genre'][genre]} movies available)")

        return recommendations
