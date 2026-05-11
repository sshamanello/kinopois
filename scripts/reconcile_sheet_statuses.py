#!/usr/bin/env python3
"""Normalize pin statuses in Google Sheets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from kinopois.config import config

try:
    import gspread
except ImportError as e:
    raise SystemExit("gspread is required. Install optional deps first.") from e

VALID = {"pending", "posted", "failed"}


@dataclass
class Stats:
    total: int = 0
    updated: int = 0
    to_posted: int = 0
    to_pending: int = 0


def main() -> int:
    if not config.google_creds_file:
        raise SystemExit("GOOGLE_CREDS_FILE is not set")
    if not config.google_sheets_id:
        raise SystemExit("GOOGLE_SHEETS_ID is not set")

    gc = gspread.service_account(filename=config.google_creds_file)
    ws = gc.open_by_key(config.google_sheets_id).worksheet(config.google_sheets_tab)

    rows: List[List[str]] = ws.get_all_values()
    if len(rows) <= 1:
        print("Sheet is empty")
        return 0

    header = rows[0]
    try:
        status_idx = header.index("status")
        posted_at_idx = header.index("posted_at")
    except ValueError as e:
        raise SystemExit("Sheet must contain 'status' and 'posted_at' columns") from e

    stats = Stats(total=len(rows) - 1)
    updates = []

    for rnum, row in enumerate(rows[1:], start=2):
        status = (row[status_idx] if status_idx < len(row) else "").strip().lower()
        posted_at = (row[posted_at_idx] if posted_at_idx < len(row) else "").strip()

        new_status = None
        if not status:
            new_status = "posted" if posted_at else "pending"
        elif status not in VALID:
            new_status = "pending"

        if new_status and new_status != status:
            updates.append(
                {
                    "range": gspread.utils.rowcol_to_a1(rnum, status_idx + 1),
                    "values": [[new_status]],
                }
            )
            stats.updated += 1
            if new_status == "posted":
                stats.to_posted += 1
            elif new_status == "pending":
                stats.to_pending += 1

    if updates:
        ws.batch_update(updates)

    print(f"total={stats.total}")
    print(f"updated={stats.updated}")
    print(f"to_posted={stats.to_posted}")
    print(f"to_pending={stats.to_pending}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
