"""Composable pipeline steps: download, process, upload, publish."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from rich.console import Console

from kinopois.config import config
from kinopois.db import get_ready_jobs, mark_failed, mark_posted, sync_pins_csv
from kinopois.export import export_movie_pins_csv
from kinopois.pinterest import publish_pin
from kinopois.processor import load_movies
from kinopois.scraper import KinopoiskScraper
from kinopois.utils import read_csv_dict, write_csv_dict

console = Console()


def step_download(limit: int) -> Path:
    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    return scraper.download_and_save(output_csv=config.cache_dir / "movies.csv", limit=limit, append_mode=True)


def step_process(input_csv: Path) -> Path:
    processor = load_movies(input_csv)
    return processor.clean(config.cache_dir / "movies_clean.csv")


def step_export(clean_csv: Path) -> Path:
    return export_movie_pins_csv(input_csv=clean_csv, output_csv=config.cache_dir / "pins.csv")


def step_upload_to_server(pins_csv: Path) -> Dict[str, int]:
    rows = read_csv_dict(pins_csv, config.csv_delimiter, config.csv_encoding)
    uploaded = 0
    failed = 0
    now_str = datetime.now().isoformat(timespec="seconds")

    for row in rows:
        kp_id = str(row.get("id", "")).strip()
        if not kp_id:
            failed += 1
            continue

        src_candidates = [
            config.framed_posters_dir / f"{kp_id}.jpg",
            config.posters_dir / f"{kp_id}.jpg",
        ]
        src = next((p for p in src_candidates if p.exists()), None)
        if not src:
            row["vds_upload_status"] = "upload_failed"
            row["error_reason"] = "source_image_not_found"
            failed += 1
            continue

        dst = config.publish_images_dir / f"{kp_id}.jpg"
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)

        row["public_image_url"] = f"{config.publish_images_base_url}/{kp_id}.jpg"
        row["remote_image_path"] = str(dst)
        row["vds_upload_status"] = "uploaded"
        row["uploaded_at"] = now_str
        row["publish_status"] = row.get("publish_status") or "ready"
        row["error_reason"] = ""
        uploaded += 1

    fieldnames = list(rows[0].keys()) if rows else []
    if fieldnames:
        write_csv_dict(pins_csv, rows, fieldnames, config.csv_delimiter, config.csv_encoding)

    return {"uploaded": uploaded, "failed": failed, "total": len(rows)}


def step_cleanup_publish_dir() -> Dict[str, int]:
    if not config.publish_images_cleanup_enabled:
        return {"deleted": 0, "kept": 0, "scanned": 0}

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

    return {"deleted": deleted, "kept": kept, "scanned": scanned}


def step_queue_sync(pins_csv: Path) -> int:
    return sync_pins_csv(pins_csv)


def step_publish(limit: int = 1) -> Dict[str, int]:
    jobs = get_ready_jobs(limit=max(1, limit))
    ok = 0
    fail = 0
    for job in jobs:
        try:
            pin_id = publish_pin(job)
            mark_posted(job["id"], pin_id)
            ok += 1
        except Exception as exc:
            mark_failed(job["id"], str(exc))
            fail += 1
    return {"ok": ok, "failed": fail, "attempted": len(jobs)}


def step_publish_one_job(job: Dict[str, str]) -> str:
    """Publish one provided job and return Pinterest pin_id."""
    return publish_pin(job)


def run_daily_prepare(limit: int) -> Dict[str, int]:
    movies_csv = step_download(limit)
    clean_csv = step_process(movies_csv)
    pins_csv = step_export(clean_csv)
    upload_stats = step_upload_to_server(pins_csv)
    cleanup_stats = step_cleanup_publish_dir()
    inserted = step_queue_sync(pins_csv)
    console.print(
        f"[green]Daily prepare done[/green]: upload={upload_stats}, cleanup={cleanup_stats}, queue_inserted={inserted}"
    )
    return {
        "download_limit": limit,
        "uploaded": upload_stats["uploaded"],
        "upload_failed": upload_stats["failed"],
        "publish_dir_deleted": cleanup_stats["deleted"],
        "queue_inserted": inserted,
    }
