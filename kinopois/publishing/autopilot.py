"""Autonomous scheduler for daily harvest and timed publish jobs."""

from __future__ import annotations

import json
import random
import subprocess
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from rich.console import Console

from kinopois.config import config
from kinopois.publishing.db import get_ready_jobs, mark_failed, mark_posted
from kinopois.publishing.eventlog import log_event
from kinopois.publishing.pipeline_steps import run_daily_prepare, step_publish_one_job

try:
    from kinopois.publishing.sheets import sync_pins_to_sheets

    _SHEETS_AVAILABLE = True
except ImportError:
    _SHEETS_AVAILABLE = False

console = Console()


class Autopilot:
    """Runs autonomous cycle: harvest once/day + post by slots."""

    def __init__(self) -> None:
        self.state_path = Path(config.autopilot_state_file)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.sleep_sec = max(10, config.autopilot_loop_sleep_sec)

    def run_forever(self) -> None:
        console.print("[bold cyan]Autopilot started[/bold cyan]")
        log_event("autopilot_started")
        self._notify("Autopilot started")
        while True:
            try:
                log_event("autopilot_tick_started")
                self.run_tick()
                log_event("autopilot_tick_completed")
            except Exception as exc:
                msg = f"Autopilot tick failed: {exc}"
                console.print(f"[red]{msg}[/red]")
                log_event("autopilot_tick_failed", error=str(exc))
                self._notify(msg)
            time.sleep(self.sleep_sec)

    def run_tick(self) -> None:
        now = datetime.now()
        state = self._load_state()
        today = now.date().isoformat()

        if state.get("day") != today:
            state = self._new_day_state(today)
            self._save_state(state)

        if not state.get("harvest_done", False):
            self._run_daily_harvest(state)
            self._save_state(state)

        slots = self._day_slots(state)
        if not config.autopilot_enable_publish:
            return
        for idx, slot_time in enumerate(slots):
            key = f"slot_{idx}"
            if state.get("posted_slots", {}).get(key):
                continue
            if now >= datetime.fromisoformat(slot_time):
                self._run_post_slot(state, key)
                self._save_state(state)

    def run_once(self) -> None:
        state = self._load_state()
        today = datetime.now().date().isoformat()
        if state.get("day") != today:
            state = self._new_day_state(today)

        if not state.get("harvest_done", False):
            self._run_daily_harvest(state)

        slots = self._day_slots(state)
        if not config.autopilot_enable_publish:
            self._save_state(state)
            return
        for idx, slot_time in enumerate(slots):
            key = f"slot_{idx}"
            if state.get("posted_slots", {}).get(key):
                continue
            if datetime.now() >= datetime.fromisoformat(slot_time):
                self._run_post_slot(state, key)

        self._save_state(state)

    def _run_daily_harvest(self, state: Dict[str, Any]) -> None:
        limit = max(1, config.autopilot_download_limit_per_day)
        console.print(f"[cyan]Daily harvest started (limit={limit})[/cyan]")
        log_event("autopilot_harvest_started", limit=limit)

        if not config.kinopoisk_api_key:
            raise RuntimeError("KINOPOISK_API_KEY is not configured")
        run_daily_prepare(limit)

        if config.autopilot_sync_sheets:
            self._sync_sheets_safe()

        state["harvest_done"] = True
        msg = "Daily harvest complete"
        console.print(f"[green]{msg}[/green]")
        log_event("autopilot_harvest_completed")
        self._notify(msg)

    def _run_post_slot(self, state: Dict[str, Any], slot_key: str) -> None:
        attempts = max(1, int(config.autopilot_publish_attempts_per_slot))
        ready_jobs = get_ready_jobs(limit=attempts)
        if not ready_jobs:
            console.print("[yellow]No ready publish jobs for slot[/yellow]")
            log_event("autopilot_slot_no_jobs", slot=slot_key)
            state.setdefault("posted_slots", {})[slot_key] = "no_jobs"
            return

        for job in ready_jobs:
            ok, result = self._publish_single_job(job)
            if ok:
                pin_id = result
                mark_posted(job["id"], pin_id)
                state.setdefault("posted_slots", {})[slot_key] = "posted"
                state["posted_count"] = int(state.get("posted_count", 0)) + 1
                console.print(f"[green]Posted job {job['id']} (pin_id={pin_id})[/green]")
                log_event("autopilot_slot_posted", slot=slot_key, job_id=job["id"], pin_id=pin_id)
                return

            error = result
            mark_failed(job["id"], error[:1500])
            log_event("autopilot_slot_job_failed", slot=slot_key, job_id=job["id"], error=error[:400])
            self._notify(f"Publish failed for job={job['id']}: {error[:180]}")

        state.setdefault("posted_slots", {})[slot_key] = "failed_all"
        console.print("[yellow]Slot ended with failures for all attempted jobs[/yellow]")

    def _publish_single_job(self, job: Dict[str, Any]) -> tuple[bool, str]:
        command = config.autopilot_publish_command.strip()
        if command:
            payload = json.dumps(job, ensure_ascii=False)
            proc = subprocess.run(
                command,
                shell=True,
                text=True,
                capture_output=True,
                input=payload,
            )
            if proc.returncode != 0:
                error = (proc.stderr or proc.stdout or "publish command failed").strip()
                return False, error
            pin_id = self._extract_pin_id(proc.stdout)
            if not pin_id:
                pin_id = f"external-{int(time.time())}"
            return True, pin_id

        try:
            pin_id = step_publish_one_job(job)
            return True, pin_id
        except Exception as exc:
            return False, str(exc).strip() or "direct publish failed"

    def _extract_pin_id(self, raw: str) -> str:
        raw = (raw or "").strip()
        if not raw:
            return ""
        try:
            data = json.loads(raw)
            return str(data.get("pin_id") or "").strip()
        except Exception:
            return raw.splitlines()[-1].strip()

    def _sync_sheets_safe(self) -> None:
        if not _SHEETS_AVAILABLE:
            console.print("[yellow]gspread is not installed, sheets sync skipped[/yellow]")
            return
        if not config.google_sheets_id:
            console.print("[yellow]GOOGLE_SHEETS_ID is not configured, sheets sync skipped[/yellow]")
            return

        stats = sync_pins_to_sheets(config.cache_dir / "pins.csv", upsert=False)
        console.print(f"[green]Sheets synced: {stats.get('total', 0)} rows[/green]")

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return self._new_day_state(date.today().isoformat())
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return self._new_day_state(date.today().isoformat())

    def _save_state(self, state: Dict[str, Any]) -> None:
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _new_day_state(self, day: str) -> Dict[str, Any]:
        return {
            "day": day,
            "harvest_done": False,
            "posted_count": 0,
            "posted_slots": {},
            "slots": self._build_slots(day),
        }

    def _day_slots(self, state: Dict[str, Any]) -> List[str]:
        slots = state.get("slots")
        if isinstance(slots, list) and slots:
            return slots

        day = str(state.get("day") or date.today().isoformat())
        slots = self._build_slots(day)
        state["slots"] = slots
        return slots

    def _build_slots(self, day: str) -> List[str]:
        hours = self._parse_slot_hours()
        max_posts = max(1, config.autopilot_posts_per_day)
        jitter = max(0, config.autopilot_slot_jitter_min)

        slots: List[str] = []
        for hour in hours[:max_posts]:
            base = datetime.fromisoformat(f"{day}T{hour:02d}:00:00")
            delta = random.randint(-jitter, jitter)
            slot = base.timestamp() + delta * 60
            slots.append(datetime.fromtimestamp(slot).isoformat(timespec="seconds"))

        slots.sort()
        return slots

    def _parse_slot_hours(self) -> List[int]:
        raw = (config.autopilot_slot_hours or "").strip()
        values: List[int] = []
        for part in raw.split(","):
            part = part.strip()
            if not part:
                continue
            try:
                hour = int(part)
            except ValueError:
                continue
            if 0 <= hour <= 23:
                values.append(hour)

        if not values:
            values = [10, 15, 20]

        # Keep stable deterministic order from config.
        return values

    def _notify(self, text: str) -> None:
        token = config.telegram_bot_token.strip()
        chat_id = config.telegram_chat_id.strip()
        if not token or not chat_id:
            return

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        try:
            requests.post(
                url,
                json={"chat_id": chat_id, "text": f"[kinopois] {text}"},
                timeout=10,
            )
        except Exception:
            # Notifications should never break pipeline.
            pass
