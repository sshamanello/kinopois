"""Composable pipeline steps: download, process, upload, publish."""

from __future__ import annotations

import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import requests
from rich.console import Console

from kinopois.config import config
from kinopois.download.scraper import KinopoiskScraper
from kinopois.processing.processor import load_movies
from kinopois.publishing.eventlog import log_event
from kinopois.publishing.export import export_movie_pins_csv
from kinopois.publishing.pinterest import publish_pin
from kinopois.publishing.postgres_queue import get_ready_jobs, mark_failed, mark_posted, sync_pins_csv
from kinopois.utils import read_csv_dict, write_csv_dict

console = Console()


def _remote_target_for_id(kp_id: str) -> str:
    return f"{config.publish_remote_user}@{config.publish_remote_host}:{config.publish_remote_dir.rstrip('/')}/{kp_id}.jpg"


def _scp_to_remote(local_path: Path, kp_id: str) -> tuple[bool, str]:
    remote = _remote_target_for_id(kp_id)
    ssh_opts = [
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "GlobalKnownHostsFile=/dev/null",
        "-o", "LogLevel=ERROR",
        "-o", f"ConnectTimeout={max(1, int(config.publish_remote_connect_timeout_sec))}",
    ]
    attempts = 3
    last_err = "remote_scp_failed"
    for idx in range(attempts):
        try:
            proc = subprocess.run(
                ["scp", *ssh_opts, str(local_path), remote],
                capture_output=True,
                text=True,
                timeout=max(3, int(config.publish_remote_cmd_timeout_sec)),
            )
        except subprocess.TimeoutExpired:
            last_err = "remote_scp_timeout"
        except Exception as exc:
            last_err = f"remote_scp_error:{exc}"
        else:
            if proc.returncode == 0:
                return True, ""
            last_err = (proc.stderr or proc.stdout or "remote_scp_failed").strip()

        if idx < attempts - 1:
            time.sleep(1.0 + idx)

    return False, last_err


def step_download(limit: int) -> Path:
    log_event("step_download_started", limit=limit)
    scraper = KinopoiskScraper(config.kinopoisk_api_key)
    out = scraper.download_and_save(output_csv=config.cache_dir / "movies.csv", limit=limit, append_mode=True)
    log_event("step_download_completed", output_csv=str(out))
    return out


def step_process(input_csv: Path) -> Path:
    log_event("step_process_started", input_csv=str(input_csv))
    processor = load_movies(input_csv)
    out = processor.clean(config.cache_dir / "movies_clean.csv")
    log_event("step_process_completed", output_csv=str(out))
    return out


def step_export(clean_csv: Path) -> Path:
    log_event("step_export_started", input_csv=str(clean_csv))
    out = export_movie_pins_csv(input_csv=clean_csv, output_csv=config.cache_dir / "pins.csv")
    log_event("step_export_completed", output_csv=str(out))
    return out


def step_upload_to_server(pins_csv: Path) -> Dict[str, int]:
    log_event("step_upload_started", pins_csv=str(pins_csv))
    rows = read_csv_dict(pins_csv, config.csv_delimiter, config.csv_encoding)
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

        if config.publish_remote_sync_enabled and config.publish_remote_host:
            ok, err = _scp_to_remote(dst, kp_id)
            if not ok:
                row["vds_upload_status"] = "upload_failed"
                row["error_reason"] = err[:500]
                failed += 1
                continue

        row["public_image_url"] = f"{config.publish_images_base_url}/{kp_id}.jpg"
        row["remote_image_path"] = str(dst)
        row["vds_upload_status"] = "uploaded"
        row["uploaded_at"] = now_str
        current_publish_status = str(row.get("publish_status", "")).strip().lower()
        if current_publish_status in {"", "pending", "failed"}:
            row["publish_status"] = "ready"
        row["error_reason"] = ""
        uploaded += 1

    fieldnames = list(rows[0].keys()) if rows else []
    if fieldnames:
        write_csv_dict(pins_csv, rows, fieldnames, config.csv_delimiter, config.csv_encoding)

    stats = {"uploaded": uploaded, "failed": failed, "skipped": skipped, "total": len(rows)}
    log_event("step_upload_completed", **stats)
    return stats


def step_cleanup_publish_dir() -> Dict[str, int]:
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

    remote_deleted = 0
    if config.publish_remote_sync_enabled and config.publish_remote_host:
        cmd = (
            f"find {config.publish_remote_dir.rstrip('/')} -type f -name '*.jpg' "
            f"-mtime +{max(1, int(config.publish_images_retention_days))} -delete -print | wc -l"
        )
        try:
            proc = subprocess.run(
                [
                    "ssh",
                    "-o", "BatchMode=yes",
                    "-o", "StrictHostKeyChecking=no",
                    "-o", f"ConnectTimeout={max(1, int(config.publish_remote_connect_timeout_sec))}",
                    f"{config.publish_remote_user}@{config.publish_remote_host}",
                    cmd,
                ],
                capture_output=True,
                text=True,
                timeout=max(3, int(config.publish_remote_cmd_timeout_sec)),
            )
            if proc.returncode == 0:
                try:
                    remote_deleted = int((proc.stdout or "0").strip().splitlines()[-1])
                except Exception:
                    remote_deleted = 0
        except Exception:
            remote_deleted = 0

    stats = {"deleted": deleted, "kept": kept, "scanned": scanned, "remote_deleted": remote_deleted}
    log_event("step_cleanup_completed", **stats)
    return stats


def step_queue_sync(pins_csv: Path) -> int:
    log_event("step_queue_sync_started", pins_csv=str(pins_csv))
    inserted = sync_pins_csv(pins_csv)
    log_event("step_queue_sync_completed", inserted=inserted)
    return inserted


def step_publish(limit: int = 1) -> Dict[str, int]:
    log_event("step_publish_started", limit=limit)
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
    movies_csv = step_download(limit)
    clean_csv = step_process(movies_csv)
    pins_csv = step_export(clean_csv)
    upload_stats = step_upload_to_server(pins_csv)
    cleanup_stats = step_cleanup_publish_dir()
    inserted = step_queue_sync(pins_csv)
    console.print(
        f"[green]Daily prepare done[/green]: upload={upload_stats}, cleanup={cleanup_stats}, queue_inserted={inserted}"
    )
    stats = {
        "download_limit": limit,
        "uploaded": upload_stats["uploaded"],
        "upload_failed": upload_stats["failed"],
        "publish_dir_deleted": cleanup_stats["deleted"],
        "queue_inserted": inserted,
    }
    log_event("run_daily_prepare_completed", **stats)
    return stats
