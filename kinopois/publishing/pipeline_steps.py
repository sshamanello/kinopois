"""Composable pipeline steps: download, process, upload, publish."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import requests
from rich.console import Console

from kinopois.config import config
from kinopois.download.scraper import KinopoiskScraper
from kinopois.processing.processor import load_movies
from kinopois.publishing.eventlog import log_event
from kinopois.publishing.movie_pins import build_movie_pin_rows
from kinopois.publishing.pinterest import publish_pin
from kinopois.publishing.postgres_queue import (
    get_ready_jobs,
    mark_failed,
    mark_posted,
    sync_pin_rows,
)
from kinopois.logging_setup import get_logger

logger = get_logger(__name__)

console = Console()


def step_download(limit: int) -> Path:
    log_event("step_download_started", limit=limit)
    logger.info("step_download started (limit=%d)", limit)
    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    out = scraper.download_and_save(output_csv=config.cache_dir / "movies.csv", limit=limit, append_mode=True)
    log_event("step_download_completed", output_csv=str(out))
    logger.info("step_download completed: %s", out)
    return out


def step_process(input_csv: Path) -> Path:
    log_event("step_process_started", input_csv=str(input_csv))
    logger.info("step_process started: %s", input_csv)
    processor = load_movies(input_csv)
    out = processor.clean(config.cache_dir / "movies_clean.csv")
    log_event("step_process_completed", output_csv=str(out))
    logger.info("step_process completed: %s", out)
    return out


def step_build_movie_pin_rows(clean_csv: Path) -> List[Dict[str, Any]]:
    log_event("step_build_pins_started", input_csv=str(clean_csv))
    pins, skip = build_movie_pin_rows(clean_csv)
    skipped_total = sum(skip.values())
    log_event(
        "step_build_pins_completed",
        pins=len(pins),
        skipped=skipped_total,
        invalid=skip["invalid"],
        missing_poster=skip["missing_poster"],
        duplicate=skip["duplicate"],
    )
    console.print(
        f"[green]Built {len(pins)} pin rows[/green] "
        f"([yellow]{skipped_total} skipped: "
        f"{skip['invalid']} invalid, "
        f"{skip['missing_poster']} missing poster, "
        f"{skip['duplicate']} duplicates[/yellow])"
    )
    return pins


def step_upload_to_server(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    log_event("step_upload_started", row_count=len(rows))
    logger.info("step_upload started (%d rows)", len(rows))
    uploaded = 0
    failed = 0
    skipped = 0
    now_str = datetime.now().isoformat(timespec="seconds")

    for row in rows:
        kp_id = str(row.get("id", "")).strip()
        if not kp_id:
            failed += 1
            continue
        dst = config.publish_images_dir / f"{kp_id}.jpg"
        already_uploaded = str(row.get("vds_upload_status", "")).strip().lower() == "uploaded"
        if already_uploaded and dst.exists():
            skipped += 1
            continue

        src_candidates = [
            config.framed_posters_dir / f"{kp_id}.jpg",
            config.posters_dir / f"{kp_id}.jpg",
        ]
        src = next((p for p in src_candidates if p.exists()), None)
        if not src:
            poster_url = str(row.get("poster_url", "")).strip()
            if poster_url:
                try:
                    config.posters_dir.mkdir(parents=True, exist_ok=True)
                    downloaded_src = config.posters_dir / f"{kp_id}.jpg"
                    resp = requests.get(poster_url, timeout=25)
                    resp.raise_for_status()
                    downloaded_src.write_bytes(resp.content)
                    src = downloaded_src
                except Exception as exc:
                    row["vds_upload_status"] = "upload_failed"
                    row["error_reason"] = f"source_download_failed:{exc}"[:500]
                    failed += 1
                    continue
            else:
                row["vds_upload_status"] = "upload_failed"
                row["error_reason"] = "source_image_not_found"
                failed += 1
                continue

        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        row["public_image_url"] = f"{config.publish_images_base_url}/{kp_id}.jpg"
        row["remote_image_path"] = str(dst)
        row["vds_upload_status"] = "uploaded"
        row["uploaded_at"] = now_str
        current_publish_status = str(row.get("publish_status", "")).strip().lower()
        if current_publish_status in {"", "pending", "failed"}:
            row["publish_status"] = "ready"
        row["error_reason"] = ""
        uploaded += 1

    stats = {"uploaded": uploaded, "failed": failed, "skipped": skipped, "total": len(rows)}
    log_event("step_upload_completed", **stats)
    return stats


def step_cleanup_publish_dir() -> Dict[str, int]:
    """Delete old images from the publish directory past the retention period."""
    if not config.publish_images_cleanup_enabled:
        stats = {"deleted": 0, "kept": 0, "scanned": 0}
        log_event("step_cleanup_skipped", **stats)
        return stats

    keep_days = max(1, int(config.publish_images_retention_days))
    cutoff_ts = datetime.now().timestamp() - keep_days * 86400
    deleted = 0
    kept = 0
    scanned = 0

    for path in config.publish_images_dir.glob("*.jpg"):
        scanned += 1
        try:
            if path.stat().st_mtime < cutoff_ts:
                path.unlink(missing_ok=True)
                deleted += 1
            else:
                kept += 1
        except Exception:
            kept += 1

    stats = {"deleted": deleted, "kept": kept, "scanned": scanned}
    log_event("step_cleanup_completed", **stats)
    return stats


def step_queue_sync(pins_csv: Path) -> int:
    log_event("step_queue_sync_started", pins_csv=str(pins_csv))
    from kinopois.utils import read_csv_dict

    rows = read_csv_dict(pins_csv, config.csv_delimiter, config.csv_encoding)
    inserted = sync_pin_rows(rows)
    log_event("step_queue_sync_completed", inserted=inserted)
    return inserted


def step_queue_sync_rows(rows: List[Dict[str, Any]]) -> int:
    log_event("step_queue_sync_rows_started", row_count=len(rows))
    inserted = sync_pin_rows(rows)
    log_event("step_queue_sync_rows_completed", inserted=inserted)
    return inserted


def step_publish(limit: int = 1) -> Dict[str, int]:
    log_event("step_publish_started", limit=limit)
    logger.info("step_publish started (limit=%d)", limit)
    jobs = get_ready_jobs(limit=max(1, limit))
    ok = 0
    fail = 0
    for job in jobs:
        internal_job_id = int(job.get("job_id") or job.get("id") or 0)
        try:
            log_event(
                "step_publish_job_started",
                job_id=internal_job_id,
                source_id=job.get("id"),
                board_id=job.get("board_id"),
                title=str(job.get("title") or "")[:120],
                image_url=str(job.get("image_url") or ""),
            )
            pin_id = publish_pin(job)
            mark_posted(internal_job_id, pin_id)
            ok += 1
            log_event(
                "step_publish_job_succeeded",
                job_id=internal_job_id,
                source_id=job.get("id"),
                pin_id=pin_id,
                board_id=job.get("board_id"),
            )
        except Exception as exc:
            error_text = str(exc)
            mark_failed(internal_job_id, error_text)
            log_event(
                "step_publish_job_failed",
                job_id=internal_job_id,
                source_id=job.get("id"),
                error=error_text[:500],
            )
            fail += 1
    log_event("step_publish_completed", attempted=len(jobs), ok=ok, failed=fail)
    return {"ok": ok, "failed": fail, "attempted": len(jobs)}


def step_publish_one_job(job: Dict[str, str]) -> str:
    """Publish one provided job and return Pinterest pin_id."""
    return publish_pin(job)


def run_daily_prepare(limit: int) -> Dict[str, int]:
    log_event("run_daily_prepare_started", limit=limit)
    logger.info("run_daily_prepare started (limit=%d)", limit)
    movies_csv = step_download(limit)
    clean_csv = step_process(movies_csv)
    pin_rows = step_build_movie_pin_rows(clean_csv)
    upload_stats = step_upload_to_server(pin_rows)
    queue_refreshed = step_queue_sync_rows(pin_rows)
    cleanup_stats = step_cleanup_publish_dir()
    console.print(
        f"[green]Daily prepare done[/green]: upload={upload_stats}, cleanup={cleanup_stats}, queue_refreshed={queue_refreshed}"
    )
    stats = {
        "download_limit": limit,
        "uploaded": upload_stats["uploaded"],
        "upload_failed": upload_stats["failed"],
        "publish_dir_deleted": cleanup_stats["deleted"],
        "queue_refreshed": queue_refreshed,
    }
    log_event("run_daily_prepare_completed", **stats)
    logger.info("run_daily_prepare completed: %s", stats)
    return stats
