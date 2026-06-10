"""PostgreSQL-backed publish queue for kinopois.

The `kinopois_pins` table is the single source of truth for the publish pipeline.
n8n reads ready rows from here; `mark_posted` / `mark_failed` update status.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

import psycopg2
from psycopg2.extras import RealDictCursor

from kinopois.config import config
from kinopois.publishing.eventlog import log_event
from kinopois.utils import read_csv_dict


# ── Connection helpers ────────────────────────────────────────────────────────

_db_initialized = False


def _conn_kwargs() -> Dict[str, Any]:
    """Build psycopg2 connection kwargs from config."""
    kwargs: Dict[str, Any] = {
        "host": config.queue_db_host,
        "port": int(config.queue_db_port),
        "dbname": config.queue_db_name,
        "user": config.queue_db_user,
        "password": config.queue_db_password,
        "cursor_factory": RealDictCursor,
    }
    sslmode = (config.queue_db_sslmode or "").strip()
    if sslmode:
        kwargs["sslmode"] = sslmode
    return kwargs


def get_conn():
    """Open a connection to the Postgres publish queue."""
    return psycopg2.connect(**_conn_kwargs())


def init_db() -> None:
    """Create the kinopois_pins table if it doesn't exist. Idempotent."""
    global _db_initialized
    if _db_initialized:
        return

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS kinopois_pins (
                    id integer PRIMARY KEY,
                    image_url text,
                    poster_url text,
                    title text,
                    original_title text,
                    year integer,
                    rating real,
                    genres text,
                    primary_genre text,
                    kp_url text,
                    source_type text,
                    description text,
                    keywords text,
                    category text,
                    board text,
                    board_id text,
                    status text,
                    created_at text,
                    posted_at text,
                    notes text,
                    public_image_url text,
                    remote_image_path text,
                    vds_upload_status text DEFAULT 'uploaded',
                    uploaded_at text,
                    publish_status text DEFAULT 'ready',
                    posted text DEFAULT 'FALSE',
                    pin_id text,
                    published_at text,
                    error_reason text,
                    updated_at timestamptz DEFAULT now()
                );
                """
            )
            for alter in (
                "ALTER TABLE kinopois_pins ADD COLUMN IF NOT EXISTS public_image_url text;",
                "ALTER TABLE kinopois_pins ADD COLUMN IF NOT EXISTS remote_image_path text;",
                "ALTER TABLE kinopois_pins ADD COLUMN IF NOT EXISTS vds_upload_status text DEFAULT 'uploaded';",
                "ALTER TABLE kinopois_pins ADD COLUMN IF NOT EXISTS uploaded_at text;",
            ):
                cur.execute(alter)
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_kinopois_pins_publish_status
                ON kinopois_pins(publish_status, posted, id);
                """
            )
        conn.commit()

    _db_initialized = True


# ── Row sync ─────────────────────────────────────────────────────────────────

def sync_pin_rows(rows: List[Dict[str, Any]]) -> int:
    """Upsert pin rows into kinopois_pins. Returns count of upserted rows."""
    init_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    inserted = 0

    with get_conn() as conn:
        with conn.cursor() as cur:
            for row in rows:
                try:
                    pin_id = int(float(str(row.get("id") or "").strip()))
                except Exception:
                    continue

                payload = {
                    "id": pin_id,
                    "image_url": str(row.get("image_url", "")).strip(),
                    "poster_url": str(row.get("poster_url", "")).strip(),
                    "title": str(row.get("title", "")).strip(),
                    "original_title": str(row.get("original_title", "")).strip(),
                    "year": int(float(row.get("year") or 0)) if str(row.get("year") or "").strip() else None,
                    "rating": float(row.get("rating") or 0) if str(row.get("rating") or "").strip() else None,
                    "genres": str(row.get("genres", "")).strip(),
                    "primary_genre": str(row.get("primary_genre", "")).strip(),
                    "kp_url": str(row.get("kp_url", "")).strip(),
                    "source_type": str(row.get("source_type", "")).strip(),
                    "description": str(row.get("description", "")).strip(),
                    "keywords": str(row.get("keywords", "")).strip(),
                    "category": str(row.get("category", "")).strip(),
                    "board": str(row.get("board", "")).strip(),
                    "board_id": str(row.get("board_id", "")).strip(),
                    "status": str(row.get("status", "")).strip() or "ready",
                    "created_at": str(row.get("created_at", "")).strip() or now,
                    "posted_at": str(row.get("posted_at", "")).strip() or "",
                    "notes": str(row.get("notes", "")).strip(),
                    "public_image_url": str(row.get("public_image_url", "")).strip(),
                    "remote_image_path": str(row.get("remote_image_path", "")).strip(),
                    "vds_upload_status": str(row.get("vds_upload_status", "")).strip() or "uploaded",
                    "uploaded_at": str(row.get("uploaded_at", "")).strip() or "",
                    "publish_status": str(row.get("publish_status", "")).strip() or "ready",
                    "posted": str(row.get("posted", "")).strip() or "FALSE",
                    "pin_id": str(row.get("pin_id", "")).strip(),
                    "published_at": str(row.get("published_at", "")).strip() or "",
                    "error_reason": str(row.get("error_reason", "")).strip(),
                    "updated_at": now,
                }

                cur.execute(
                    """
                    INSERT INTO kinopois_pins (
                        id, image_url, poster_url, title, original_title, year, rating, genres, primary_genre,
                        kp_url, source_type, description, keywords, category, board, board_id, status,
                        created_at, posted_at, notes, public_image_url, remote_image_path, vds_upload_status,
                        uploaded_at, publish_status, posted, pin_id, published_at,
                        error_reason, updated_at
                    )
                    VALUES (
                        %(id)s, %(image_url)s, %(poster_url)s, %(title)s, %(original_title)s, %(year)s, %(rating)s,
                        %(genres)s, %(primary_genre)s, %(kp_url)s, %(source_type)s, %(description)s, %(keywords)s,
                        %(category)s, %(board)s, %(board_id)s, %(status)s, %(created_at)s, %(posted_at)s,
                        %(notes)s, %(public_image_url)s, %(remote_image_path)s, %(vds_upload_status)s,
                        %(uploaded_at)s, %(publish_status)s, %(posted)s, %(pin_id)s, %(published_at)s, %(error_reason)s,
                        %(updated_at)s
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        image_url = EXCLUDED.image_url,
                        poster_url = EXCLUDED.poster_url,
                        title = EXCLUDED.title,
                        original_title = EXCLUDED.original_title,
                        year = EXCLUDED.year,
                        rating = EXCLUDED.rating,
                        genres = EXCLUDED.genres,
                        primary_genre = EXCLUDED.primary_genre,
                        kp_url = EXCLUDED.kp_url,
                        source_type = EXCLUDED.source_type,
                        description = EXCLUDED.description,
                        keywords = EXCLUDED.keywords,
                        category = EXCLUDED.category,
                        board = EXCLUDED.board,
                        board_id = EXCLUDED.board_id,
                        status = CASE
                            WHEN kinopois_pins.status IS NULL OR kinopois_pins.status = '' THEN EXCLUDED.status
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.status
                            ELSE EXCLUDED.status
                        END,
                        created_at = COALESCE(kinopois_pins.created_at, EXCLUDED.created_at),
                        posted_at = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.posted_at
                            ELSE COALESCE(NULLIF(EXCLUDED.posted_at, ''), kinopois_pins.posted_at)
                        END,
                        notes = EXCLUDED.notes,
                        public_image_url = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.public_image_url
                            ELSE COALESCE(NULLIF(EXCLUDED.public_image_url, ''), kinopois_pins.public_image_url)
                        END,
                        remote_image_path = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.remote_image_path
                            ELSE COALESCE(NULLIF(EXCLUDED.remote_image_path, ''), kinopois_pins.remote_image_path)
                        END,
                        vds_upload_status = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.vds_upload_status
                            ELSE COALESCE(NULLIF(EXCLUDED.vds_upload_status, ''), kinopois_pins.vds_upload_status)
                        END,
                        uploaded_at = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.uploaded_at
                            ELSE COALESCE(NULLIF(EXCLUDED.uploaded_at, ''), kinopois_pins.uploaded_at)
                        END,
                        publish_status = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.publish_status
                            ELSE EXCLUDED.publish_status
                        END,
                        posted = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.posted
                            ELSE EXCLUDED.posted
                        END,
                        pin_id = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.pin_id
                            ELSE COALESCE(NULLIF(EXCLUDED.pin_id, ''), kinopois_pins.pin_id)
                        END,
                        published_at = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.published_at
                            ELSE COALESCE(NULLIF(EXCLUDED.published_at, ''), kinopois_pins.published_at)
                        END,
                        error_reason = CASE
                            WHEN lower(coalesce(kinopois_pins.publish_status, '')) IN ('published', 'failed')
                                 OR upper(coalesce(kinopois_pins.posted, '')) = 'TRUE' THEN kinopois_pins.error_reason
                            ELSE EXCLUDED.error_reason
                        END,
                        updated_at = EXCLUDED.updated_at
                    """,
                    payload,
                )
                inserted += 1
        conn.commit()
    return inserted


def _is_terminal_status(status: str, posted: str) -> bool:
    """Check if a row is in a terminal state (published or failed)."""
    return str(posted).strip().upper() == "TRUE" or str(status).strip().lower() in {"published", "failed"}


def sync_pins_csv(pins_csv_path) -> int:
    """Load a pins CSV and upsert rows into the Postgres queue."""
    rows = read_csv_dict(pins_csv_path, config.csv_delimiter, config.csv_encoding)
    return sync_pin_rows(rows)


# ── Queue queries ────────────────────────────────────────────────────────────

def get_ready_jobs(limit: int = 20) -> List[Dict[str, Any]]:
    """Return ready-to-publish jobs ordered by id."""
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM kinopois_pins
                WHERE publish_status = 'ready'
                  AND upper(coalesce(posted, '')) <> 'TRUE'
                  AND lower(coalesce(vds_upload_status, 'uploaded')) = 'uploaded'
                  AND coalesce(id::text, '') <> ''
                  AND coalesce(title, original_title, description, '') <> ''
                ORDER BY id ASC
                LIMIT %s
                """,
                (max(1, int(limit)),),
            )
            rows = [dict(r) for r in cur.fetchall()]
    return rows


def mark_posted(job_id: int, pin_id: str) -> None:
    """Mark a job as successfully posted."""
    now = datetime.utcnow().isoformat(timespec="seconds")
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kinopois_pins
                SET posted='TRUE',
                    publish_status='published',
                    status='posted',
                    pin_id=%s,
                    published_at=%s,
                    posted_at=COALESCE(NULLIF(posted_at, ''), %s),
                    error_reason='',
                    updated_at=now()
                WHERE id=%s
                """,
                (str(pin_id), now, now, int(job_id)),
            )
        conn.commit()
    log_event("publish_job_marked_posted", job_id=job_id, pin_id=pin_id, posted_at=now)


def mark_failed(job_id: int, error: str) -> None:
    """Mark a job as failed."""
    error_text = (error or "").strip()
    now = datetime.utcnow().isoformat(timespec="seconds")
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE kinopois_pins
                SET posted='FALSE',
                    publish_status='failed',
                    status='failed',
                    error_reason=%s,
                    updated_at=now()
                WHERE id=%s
                """,
                (error_text[:2000], int(job_id)),
            )
        conn.commit()
    log_event("publish_job_marked_failed", job_id=job_id, error=error_text[:500], failed_at=now)


def db_counts() -> Dict[str, int]:
    """Return counts by publish status."""
    init_db()
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (WHERE publish_status='ready' AND upper(coalesce(posted,'')) <> 'TRUE') AS ready,
                    COUNT(*) FILTER (WHERE publish_status='published' OR upper(coalesce(posted,''))='TRUE') AS posted,
                    COUNT(*) FILTER (WHERE publish_status='failed') AS failed,
                    COUNT(*) AS total
                FROM kinopois_pins
                """
            )
            row = cur.fetchone() or {}
    return {
        "ready": int(row.get("ready", 0) or 0),
        "posted": int(row.get("posted", 0) or 0),
        "failed": int(row.get("failed", 0) or 0),
        "total": int(row.get("total", 0) or 0),
    }


def claim_ready_jobs(limit: int = 1) -> List[Dict[str, Any]]:
    """Atomically claim ready jobs for publishing (SKIP LOCKED)."""
    init_db()
    now = datetime.utcnow().isoformat(timespec="seconds")
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM kinopois_pins
                WHERE publish_status='ready'
                  AND upper(coalesce(posted,'')) <> 'TRUE'
                  AND lower(coalesce(vds_upload_status, 'uploaded')) = 'uploaded'
                ORDER BY id ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (max(1, int(limit)),),
            )
            rows = [dict(r) for r in cur.fetchall()]
            if not rows:
                conn.commit()
                return []
            ids = [int(r["id"]) for r in rows]
            cur.execute(
                """
                UPDATE kinopois_pins
                SET status='processing',
                    updated_at=now()
                WHERE id = ANY(%s)
                """,
                (ids,),
            )
        conn.commit()
    log_event("publish_jobs_claimed", count=len(rows), job_ids=ids)
    return rows