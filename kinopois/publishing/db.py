"""SQLite storage for movie cache tables and legacy helpers."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from kinopois.config import config
from kinopois.publishing.eventlog import log_event
from kinopois.publishing import postgres_queue as queue
from kinopois.utils import read_csv_dict


def _db_path(db_path: Optional[Path] = None) -> Path:
    return db_path or (config.cache_dir / "kinopois.db")


def get_conn(db_path: Optional[Path] = None) -> sqlite3.Connection:
    path = _db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[Path] = None) -> Path:
    path = _db_path(db_path)
    with get_conn(path) as conn:
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

            CREATE TABLE IF NOT EXISTS publish_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT UNIQUE,
                dedupe_key TEXT NOT NULL UNIQUE,
                image_url TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                keywords TEXT,
                board TEXT,
                board_id TEXT,
                link TEXT,
                source_row_json TEXT,
                status TEXT NOT NULL DEFAULT 'ready',
                pinterest_pin_id TEXT,
                error TEXT,
                retries INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                posted_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_movies_raw_title ON movies_raw(title);
            CREATE INDEX IF NOT EXISTS idx_movies_clean_genre ON movies_clean(primary_genre);
            CREATE INDEX IF NOT EXISTS idx_collages_genre ON collages(genre);
            CREATE INDEX IF NOT EXISTS idx_publish_jobs_status_created
            ON publish_jobs(status, created_at);
            """
        )
        existing_columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(publish_jobs)").fetchall()
        }
        if "source_id" not in existing_columns:
            conn.execute("ALTER TABLE publish_jobs ADD COLUMN source_id TEXT;")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_publish_jobs_source_id ON publish_jobs(source_id);")
    return path


def _dedupe_key(row: Dict[str, Any]) -> str:
    base = "|".join(
        [
            str(row.get("image_url", "")).strip(),
            str(row.get("title", "")).strip(),
            str(row.get("board_id", row.get("board", ""))).strip(),
        ]
    )
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def _movie_source_id(row: Dict[str, Any]) -> str:
    base = "|".join([
        str(row.get("id", "")).strip(),
        str(row.get("title", "")).strip(),
        str(row.get("poster_file", "")).strip(),
    ])
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def sync_movies_raw_csv(csv_path: Path, db_path: Optional[Path] = None) -> int:
    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
    return sync_movies_raw_rows(rows, db_path=db_path)


def sync_movies_raw_rows(rows: List[Dict[str, Any]], db_path: Optional[Path] = None) -> int:
    init_db(db_path)
    now = datetime.utcnow().isoformat(timespec="seconds")
    inserted = 0
    with get_conn(db_path) as conn:
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


def sync_movies_clean_csv(csv_path: Path, db_path: Optional[Path] = None) -> int:
    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
    return sync_movies_clean_rows(rows, db_path=db_path)


def sync_movies_clean_rows(rows: List[Dict[str, Any]], db_path: Optional[Path] = None) -> int:
    init_db(db_path)
    now = datetime.utcnow().isoformat(timespec="seconds")
    inserted = 0
    with get_conn(db_path) as conn:
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


def sync_collages_csv(csv_path: Path, db_path: Optional[Path] = None) -> int:
    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
    return sync_collages_rows(rows, db_path=db_path)


def sync_collages_rows(rows: List[Dict[str, Any]], db_path: Optional[Path] = None) -> int:
    init_db(db_path)
    now = datetime.utcnow().isoformat(timespec="seconds")
    inserted = 0
    with get_conn(db_path) as conn:
        for row in rows:
            dkey = hashlib.sha1((str(row.get('genre','')) + '|' + str(row.get('collage_file','')) + '|' + str(row.get('film1','')) + '|' + str(row.get('film2','')) + '|' + str(row.get('film3','')) + '|' + str(row.get('film4',''))).encode('utf-8')).hexdigest()
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


def sync_pins_csv(
    pins_csv: Path,
    db_path: Optional[Path] = None,
) -> int:
    del db_path
    rows = read_csv_dict(pins_csv, config.csv_delimiter, config.csv_encoding)
    return queue.sync_pin_rows(rows)


def sync_publish_job_rows(rows: List[Dict[str, Any]], db_path: Optional[Path] = None) -> int:
    del db_path
    return queue.sync_pin_rows(rows)


def get_ready_jobs(limit: int = 20, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    del db_path
    return queue.get_ready_jobs(limit=limit)


def claim_ready_jobs(limit: int = 1, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Atomically claim ready jobs for publishing."""
    del db_path
    return queue.claim_ready_jobs(limit=limit)


def mark_posted(job_id: int, pin_id: str, db_path: Optional[Path] = None) -> None:
    del db_path
    queue.mark_posted(job_id, pin_id)


def mark_failed(job_id: int, error: str, db_path: Optional[Path] = None) -> None:
    del db_path
    queue.mark_failed(job_id, error)


def sync_all_from_csv(cache_dir: Optional[Path] = None, db_path: Optional[Path] = None) -> Dict[str, int]:
    cdir = cache_dir or config.cache_dir
    init_db(db_path)
    out = {"movies_raw": 0, "movies_clean": 0, "collages": 0, "publish_jobs": 0}
    raw_csv = cdir / "movies.csv"
    clean_csv = cdir / "movies_clean.csv"
    collages_csv = cdir / "collages.csv"
    pins_csv = cdir / "pins.csv"
    if raw_csv.exists():
        out["movies_raw"] = sync_movies_raw_csv(raw_csv, db_path)
    if clean_csv.exists():
        out["movies_clean"] = sync_movies_clean_csv(clean_csv, db_path)
    if collages_csv.exists():
        out["collages"] = sync_collages_csv(collages_csv, db_path)
    return out


def db_counts(db_path: Optional[Path] = None) -> Dict[str, int]:
    del db_path
    return queue.db_counts()
