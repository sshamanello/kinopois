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
    init_db(db_path)
    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
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
    init_db(db_path)
    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
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
    init_db(db_path)
    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
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
    init_db(db_path)
    rows = read_csv_dict(pins_csv, config.csv_delimiter, config.csv_encoding)
    now = datetime.utcnow().isoformat(timespec="seconds")
    inserted = 0

    with get_conn(db_path) as conn:
        for row in rows:
            dkey = _dedupe_key(row)
            payload = {
                "dedupe_key": dkey,
                "image_url": row.get("image_url", "").strip(),
                "title": row.get("title", "").strip(),
                "description": row.get("description", "").strip(),
                "keywords": row.get("keywords", "").strip(),
                "board": row.get("board", "").strip(),
                "board_id": row.get("board_id", "").strip(),
                "link": row.get("link", "").strip(),
                "source_row_json": json.dumps(row, ensure_ascii=False),
                "created_at": now,
                "updated_at": now,
            }
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO publish_jobs
                (dedupe_key, image_url, title, description, keywords, board, board_id, link,
                 source_row_json, status, created_at, updated_at)
                VALUES
                (:dedupe_key, :image_url, :title, :description, :keywords, :board, :board_id, :link,
                 :source_row_json, 'ready', :created_at, :updated_at)
                """,
                payload,
            )
            inserted += cur.rowcount
    return inserted


def get_ready_jobs(limit: int = 20, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    init_db(db_path)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            SELECT id, image_url, title, description, keywords, board, board_id, link, source_row_json
            FROM publish_jobs
            WHERE status='ready'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows: List[Dict[str, Any]] = []
        for r in cur.fetchall():
            row = dict(r)
            source = {}
            raw_source = row.pop("source_row_json", "") or ""
            if raw_source:
                try:
                    source = json.loads(raw_source)
                except json.JSONDecodeError:
                    source = {}
            merged = {
                "job_id": int(row["id"]),
                "id": str(source.get("id") or row["id"]),
                "title": str(source.get("title") or row.get("title") or "").strip(),
                "original_title": str(source.get("original_title") or source.get("title") or row.get("title") or "").strip(),
                "description": str(source.get("description") or row.get("description") or "").strip(),
                "keywords": str(source.get("keywords") or row.get("keywords") or "").strip(),
                "board": str(source.get("board") or row.get("board") or "").strip(),
                "board_id": str(source.get("board_id") or row.get("board_id") or "").strip(),
                "kp_url": str(source.get("kp_url") or row.get("link") or "").strip(),
                "image_url": str(source.get("image_url") or row.get("image_url") or "").strip(),
                "publish_status": "ready",
                "vds_upload_status": "uploaded",
            }
            rows.append(merged)
        return rows


def claim_ready_jobs(limit: int = 1, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Atomically claim ready jobs for publishing."""
    init_db(db_path)
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute(
            """
            SELECT id, image_url, title, description, keywords, board, board_id, link, source_row_json
            FROM publish_jobs
            WHERE status='ready'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows: List[Dict[str, Any]] = []
        for r in cur.fetchall():
            row = dict(r)
            source = {}
            raw_source = row.pop("source_row_json", "") or ""
            if raw_source:
                try:
                    source = json.loads(raw_source)
                except json.JSONDecodeError:
                    source = {}
            rows.append(
                {
                    "job_id": int(row["id"]),
                    "id": str(source.get("id") or row["id"]),
                    "title": str(source.get("title") or row.get("title") or "").strip(),
                    "original_title": str(source.get("original_title") or source.get("title") or row.get("title") or "").strip(),
                    "description": str(source.get("description") or row.get("description") or "").strip(),
                    "keywords": str(source.get("keywords") or row.get("keywords") or "").strip(),
                    "board": str(source.get("board") or row.get("board") or "").strip(),
                    "board_id": str(source.get("board_id") or row.get("board_id") or "").strip(),
                    "kp_url": str(source.get("kp_url") or row.get("link") or "").strip(),
                    "image_url": str(source.get("image_url") or row.get("image_url") or "").strip(),
                    "publish_status": "ready",
                    "vds_upload_status": "uploaded",
                }
            )
        if not rows:
            conn.commit()
            return []
        ids = [int(r["job_id"]) for r in rows]
        conn.executemany(
            "UPDATE publish_jobs SET status='processing', updated_at=? WHERE id=?",
            [(now, job_id) for job_id in ids],
        )
        conn.commit()
    log_event("publish_jobs_claimed", count=len(rows), job_ids=ids)
    return rows


def mark_posted(job_id: int, pin_id: str, db_path: Optional[Path] = None) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE publish_jobs
            SET status='posted', pinterest_pin_id=?, posted_at=?, updated_at=?, error=NULL
            WHERE id=?
            """,
            (pin_id, now, now, job_id),
        )
    log_event("publish_job_marked_posted", job_id=job_id, pin_id=pin_id, posted_at=now)


def mark_failed(job_id: int, error: str, db_path: Optional[Path] = None) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    error_text = (error or "").strip()
    with get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE publish_jobs
            SET status='failed', error=?, retries=retries+1, updated_at=?
            WHERE id=?
            """,
            (error_text[:2000], now, job_id),
        )
    log_event("publish_job_marked_failed", job_id=job_id, error=error_text[:500], failed_at=now)


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
    init_db(db_path)
    with get_conn(db_path) as conn:
        return {
            "movies_raw": conn.execute("SELECT COUNT(*) FROM movies_raw").fetchone()[0],
            "movies_clean": conn.execute("SELECT COUNT(*) FROM movies_clean").fetchone()[0],
            "collages": conn.execute("SELECT COUNT(*) FROM collages").fetchone()[0],
            "ready": conn.execute("SELECT COUNT(*) FROM publish_jobs WHERE status='ready'").fetchone()[0],
            "posted": conn.execute("SELECT COUNT(*) FROM publish_jobs WHERE status='posted'").fetchone()[0],
            "failed": conn.execute("SELECT COUNT(*) FROM publish_jobs WHERE status='failed'").fetchone()[0],
        }
