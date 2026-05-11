"""Google Sheets sync for movie pins CSV."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from kinopois.config import config
from kinopois.utils import read_csv_dict

logger = logging.getLogger(__name__)

# Column order that matches pins.csv _MOVIE_PIN_FIELDNAMES
SHEET_HEADERS = [
    "id", "image_url", "poster_url", "title", "original_title",
    "year", "rating", "genres", "primary_genre", "kp_url", "source_type",
    "description", "keywords", "category", "board", "board_id",
    "status", "created_at", "posted_at", "notes",
    "public_image_url", "remote_image_path", "vds_upload_status",
    "uploaded_at", "publish_status", "published_at", "error_reason",
]


def _get_client():
    """Return authenticated gspread client using service account JSON."""
    try:
        import gspread
    except ImportError:
        raise ImportError(
            "gspread is not installed. Run: pip install gspread google-auth"
        )

    creds_file = config.google_creds_file
    if not creds_file or not Path(creds_file).exists():
        raise FileNotFoundError(
            f"Google service account JSON not found: {creds_file!r}\n"
            "Set GOOGLE_CREDS_FILE in .env to the path of your service account key."
        )

    return gspread.service_account(filename=str(creds_file))


def _get_worksheet(gc):
    """Open the configured spreadsheet and return the target worksheet."""
    sheets_id = config.google_sheets_id
    tab_name = config.google_sheets_tab

    if not sheets_id:
        raise ValueError(
            "GOOGLE_SHEETS_ID is not set. Add it to .env"
        )

    try:
        sh = gc.open_by_key(sheets_id)
    except Exception as e:
        raise RuntimeError(f"Cannot open spreadsheet {sheets_id!r}: {e}") from e

    try:
        ws = sh.worksheet(tab_name)
    except Exception:
        # Tab doesn't exist yet — create it
        ws = sh.add_worksheet(title=tab_name, rows=5000, cols=len(SHEET_HEADERS))

    return ws


def _ensure_header(ws) -> None:
    """Write header row if the sheet is empty or header is missing."""
    try:
        first_row = ws.row_values(1)
    except Exception:
        first_row = []

    if first_row != SHEET_HEADERS:
        ws.update("A1", [SHEET_HEADERS])


def sync_pins_to_sheets(
    csv_path: Optional[Path] = None,
    *,
    upsert: bool = False,
) -> Dict[str, int]:
    """Sync pins CSV to Google Sheets.

    Reads ``csv_path`` (defaults to ``config.cache_dir/pins.csv``),
    looks up existing rows by ``id`` column, and:
    - appends rows that don't exist yet (new pins)
    - skips rows that already exist when ``upsert=False`` (default)
    - overwrites existing rows when ``upsert=True``

    Returns:
        dict with keys: added, updated, skipped, total
    """
    from rich.console import Console
    console = Console()

    if csv_path is None:
        csv_path = config.cache_dir / "pins.csv"

    if not Path(csv_path).exists():
        raise FileNotFoundError(f"pins.csv not found: {csv_path}")

    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
    if not rows:
        console.print("[yellow]pins.csv is empty — nothing to sync[/yellow]")
        return {"added": 0, "updated": 0, "skipped": 0, "total": 0}

    gc = _get_client()
    ws = _get_worksheet(gc)
    _ensure_header(ws)

    # Read existing data once (batch, avoid per-cell API calls)
    existing_data = ws.get_all_records(expected_headers=SHEET_HEADERS)
    existing_by_id: Dict[str, int] = {
        str(r.get("id", "")): idx + 2  # +2: row 1 is header, gspread is 1-indexed
        for idx, r in enumerate(existing_data)
        if r.get("id")
    }

    to_append: List[List[Any]] = []
    to_update: List[tuple] = []  # (row_number, values)
    skipped = 0

    for row in rows:
        pin_id = str(row.get("id", "")).strip()
        if not pin_id:
            skipped += 1
            continue

        values = [str(row.get(h, "")) for h in SHEET_HEADERS]

        if pin_id in existing_by_id:
            if upsert:
                to_update.append((existing_by_id[pin_id], values))
            else:
                skipped += 1
        else:
            to_append.append(values)

    # Batch append new rows (single API call)
    if to_append:
        ws.append_rows(to_append, value_input_option="USER_ENTERED")

    # Batch update existing rows using batch_update (single API call)
    if to_update:
        import gspread

        data = [
            {
                "range": f"{gspread.utils.rowcol_to_a1(row_num, 1)}:{gspread.utils.rowcol_to_a1(row_num, len(SHEET_HEADERS))}",
                "values": [values],
            }
            for row_num, values in to_update
        ]
        ws.batch_update(data, value_input_option="USER_ENTERED")

    stats = {
        "added": len(to_append),
        "updated": len(to_update),
        "skipped": skipped,
        "total": len(rows),
    }

    console.print(
        f"[green]Sheets sync:[/green] "
        f"{stats['added']} added, {stats['updated']} updated, "
        f"{stats['skipped']} skipped (total {stats['total']})"
    )
    return stats


def normalize_sheet_statuses() -> Dict[str, int]:
    """Normalize status column values in sheet without touching explicit states."""
    gc = _get_client()
    ws = _get_worksheet(gc)
    _ensure_header(ws)

    rows = ws.get_all_values()
    if len(rows) <= 1:
        return {"total": 0, "updated": 0, "to_posted": 0, "to_pending": 0}

    header = rows[0]
    status_idx = header.index("status")
    posted_at_idx = header.index("posted_at")

    valid = {"pending", "posted", "failed"}
    updates = []
    stats = {"total": len(rows) - 1, "updated": 0, "to_posted": 0, "to_pending": 0}

    for rnum, row in enumerate(rows[1:], start=2):
        status = (row[status_idx] if status_idx < len(row) else "").strip().lower()
        posted_at = (row[posted_at_idx] if posted_at_idx < len(row) else "").strip()

        new_status = None
        if not status:
            new_status = "posted" if posted_at else "pending"
        elif status not in valid:
            new_status = "pending"

        if new_status and new_status != status:
            updates.append(
                {
                    "range": f"{chr(ord('A') + status_idx)}{rnum}",
                    "values": [[new_status]],
                }
            )
            stats["updated"] += 1
            if new_status == "posted":
                stats["to_posted"] += 1
            else:
                stats["to_pending"] += 1

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")

    return stats


def sync_upload_fields_to_sheets(csv_path: Optional[Path] = None) -> Dict[str, int]:
    """Sync only upload-related fields by id, preserving content/status fields."""
    from rich.console import Console
    import gspread

    console = Console()
    if csv_path is None:
        csv_path = config.cache_dir / "pins.csv"
    if not Path(csv_path).exists():
        raise FileNotFoundError(f"pins.csv not found: {csv_path}")

    rows = read_csv_dict(csv_path, config.csv_delimiter, config.csv_encoding)
    if not rows:
        return {"updated": 0, "skipped": 0, "total": 0}

    gc = _get_client()
    ws = _get_worksheet(gc)
    _ensure_header(ws)

    sheet_rows = ws.get_all_records(expected_headers=SHEET_HEADERS)
    sheet_by_id = {str(r.get("id", "")).strip(): idx + 2 for idx, r in enumerate(sheet_rows) if r.get("id")}

    fields = ["image_url", "public_image_url", "remote_image_path", "vds_upload_status", "uploaded_at", "publish_status", "error_reason"]
    updates = []
    updated = 0
    skipped = 0

    for row in rows:
        pid = str(row.get("id", "")).strip()
        if not pid or pid not in sheet_by_id:
            skipped += 1
            continue
        rnum = sheet_by_id[pid]
        for f in fields:
            cnum = SHEET_HEADERS.index(f) + 1
            updates.append(
                {
                    "range": gspread.utils.rowcol_to_a1(rnum, cnum),
                    "values": [[str(row.get(f, ""))]],
                }
            )
        updated += 1

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")

    stats = {"updated": updated, "skipped": skipped, "total": len(rows)}
    console.print(f"[green]Upload fields sync:[/green] {updated} updated, {skipped} skipped (total {len(rows)})")
    return stats
