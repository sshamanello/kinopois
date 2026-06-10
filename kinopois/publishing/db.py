"""SQLite cache for movie and collage data.

This module manages the local SQLite cache (movies_raw, movies_clean, collages).
The publish queue lives in Postgres — see postgres_queue.py.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from kinopois.config import config
from kinopois.publishing.eventlog import log_event
from kinopois.utils import read_csv_dict


def _db_path() -> Path:
    """Return the SQLite database path (always under config.cache_dir)."""
    return config.cache_dir / "kinopois.db"


def get_conn() -> sqlite3.Connection:
    """Open a connection to the local SQLite cache."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> Path:
    """Create SQLite cache tables if they don't exist."""
    path = _db_path()
    with get_conn() as conn:
        conn.executescript(
            """
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS movies_raw (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT UNIQUE,
                title TEXT,
                genres TEXT,
                rating_kp REAL,
                poster_file TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS movies_clean (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT UNIQUE,
                title TEXT,
                genres TEXT,
                primary_genre TEXT,
                rating_kp REAL,
                poster_file TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS collages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dedupe_key TEXT NOT NULL UNIQUE,
                genre TEXT,
                collage_file TEXT,
                film1 TEXT,
                film2 TEXT,
                film3 TEXT,
                film4 TEXT,
                payload_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_movies_raw_title ON movies_raw(title);
            CREATE INDEX IF NOT EXISTS idx_movies_clean_genre ON movies_clean(primary_genre);
            CREATE INDEX IF NOT EXISTS idx_collages_genre ON collages(genre);
            """
        )
    return path


def _movie_source_id(row: Dict[str, Any]) -> str:
    """Deterministic hash for deduplication of movie rows."""
    base = "|".join([
        str(row.get("id", "")).strip(),
        str(row.get("title", "")).strip(),
        str(row.get("poster_file", "")).strip(),
    ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def sync_movies_raw_rows(rows: List[Dict[str, Any]]) -> int:
    """Upsert raw movie rows into SQLite cache. Returns count of inserted rows."""
    init_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    inserted = 0
    with get_conn() as conn:
        for row in rows:
            sid = _movie_source_id(row)
            cur = conn.execute(
                """
                INSERT OR REPLACE INTO movies_raw
                (source_id, title, genres, rating_kp, poster_file, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM movies_raw WHERE source_id=?), ?), ?)
                """,
                (
                    sid,
                    row.get("title", "").strip(),
                    row.get("genres", "").strip(),
                    float(row.get("rating_kp") or 0),
                    row.get("poster_file", "").strip(),
                    json.dumps(row, ensure_ascii=False),
                    sid,
                    now,
                    now,
                ),
            )
            inserted += 1 if cur.rowcount else 0
    return inserted


def sync_movies_raw_csv(csv_path: Path) -> int:
    """Load movies CSV and upsert into SQLite cache."""
    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
    return sync_movies_raw_rows(rows)


def sync_movies_clean_rows(rows: List[Dict[str, Any]]) -> int:
    """Upsert cleaned movie rows into SQLite cache. Returns count of inserted rows."""
    init_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    inserted = 0
    with get_conn() as conn:
        for row in rows:
            sid = _movie_source_id(row)
            cur = conn.execute(
                """
                INSERT OR REPLACE INTO movies_clean
                (source_id, title, genres, primary_genre, rating_kp, poster_file, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM movies_clean WHERE source_id=?), ?), ?)
                """,
                (
                    sid,
                    row.get("title", "").strip(),
                    row.get("genres", "").strip(),
                    row.get("primary_genre", "").strip(),
                    float(row.get("rating_kp") or 0),
                    row.get("poster_file", "").strip(),
                    json.dumps(row, ensure_ascii=False),
                    sid,
                    now,
                    now,
                ),
            )
            inserted += 1 if cur.rowcount else 0
    return inserted


def sync_movies_clean_csv(csv_path: Path) -> int:
    """Load cleaned movies CSV and upsert into SQLite cache."""
    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
    return sync_movies_clean_rows(rows)


def sync_collages_rows(rows: List[Dict[str, Any]]) -> int:
    """Upsert collage rows into SQLite cache. Returns count of inserted rows."""
    init_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    inserted = 0
    with get_conn() as conn:
        for row in rows:
            dkey = hashlib.sha1(
                (
                    str(row.get("genre", "")) + "|"
                    + str(row.get("collage_file", "")) + "|"
                    + str(row.get("film1", "")) + "|"
                    + str(row.get("film2", "")) + "|"
                    + str(row.get("film3", "")) + "|"
                    + str(row.get("film4", ""))
                ).encode("utf-8")
            ).hexdigest()
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO collages
                (dedupe_key, genre, collage_file, film1, film2, film3, film4, payload_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    dkey,
                    row.get("genre", "").strip(),
                    row.get("collage_file", "").strip(),
                    row.get("film1", "").strip(),
                    row.get("film2", "").strip(),
                    row.get("film3", "").strip(),
                    row.get("film4", "").strip(),
                    json.dumps(row, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            inserted += cur.rowcount
    return inserted


def sync_collages_csv(csv_path: Path) -> int:
    """Load collages CSV and upsert into SQLite cache."""
    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
    return sync_collages_rows(rows)


def sync_all_from_csv(cache_dir: Optional[Path] = None) -> Dict[str, int]:
    """Sync all CSV artifacts into SQLite cache. Returns dict of table -> row count."""
    cdir = cache_dir or config.cache_dir
    init_db()
    out: Dict[str, int] = {"movies_raw": 0, "movies_clean": 0, "collages": 0}
    raw_csv = cdir / "movies.csv"
    clean_csv = cdir / "movies_clean.csv"
    collages_csv = cdir / "collages.csv"
    if raw_csv.exists():
        out["movies_raw"] = sync_movies_raw_csv(raw_csv)
    if clean_csv.exists():
        out["movies_clean"] = sync_movies_clean_csv(clean_csv)
    if collages_csv.exists():
        out["collages"] = sync_collages_csv(collages_csv)
    return out