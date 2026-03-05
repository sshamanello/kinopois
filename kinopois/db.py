"""SQLite queue storage for Pinterest publishing."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from kinopois.config import config
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
            SELECT id, image_url, title, description, keywords, board, board_id, link
            FROM publish_jobs
            WHERE status='ready'
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]


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


def mark_failed(job_id: int, error: str, db_path: Optional[Path] = None) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn(db_path) as conn:
        conn.execute(
            """
            UPDATE publish_jobs
            SET status='failed', error=?, retries=retries+1, updated_at=?
            WHERE id=?
            """,
            (error[:2000], now, job_id),
        )
