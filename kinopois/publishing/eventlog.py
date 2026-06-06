"""Structured event logging for pipeline observability."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from kinopois.config import config


def _log_path() -> Path:
    path = config.data_dir / "logs" / "events.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def log_event(event: str, **payload: Any) -> None:
    entry: Dict[str, Any] = {
        "ts": datetime.now().isoformat(timespec="seconds"),
        "event": event,
    }
    entry.update(payload)
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        # Logging must never break pipeline execution.
        return

