"""Utility functions for kinopois."""

import csv
import re
from pathlib import Path
from typing import Any, Dict, List


def safe_filename(name: str) -> str:
    """Convert string to safe filename."""
    # Replace non-alphanumeric chars with underscore
    safe = re.sub(r"[^0-9A-Za-zА-Яа-я]+", "_", name)
    return safe.strip("_") or "unnamed"


def read_csv_dict(
    filepath: Path,
    delimiter: str = ";",
    encoding: str = "utf-8-sig",
) -> List[Dict[str, Any]]:
    """Read CSV file and return list of dictionaries."""
    if not filepath.exists():
        return []

    with open(filepath, "r", encoding=encoding) as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        return list(reader)


def write_csv_dict(
    filepath: Path,
    rows: List[Dict[str, Any]],
    fieldnames: List[str],
    delimiter: str = ";",
    encoding: str = "utf-8-sig",
) -> None:
    """Write list of dictionaries to CSV file."""
    filepath.parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, "w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
        writer.writeheader()
        writer.writerows(rows)


def parse_rating(rating_str: str) -> float:
    """Parse rating string to float, handling comma as decimal separator."""
    if not rating_str:
        return 0.0
    cleaned = rating_str.strip().replace(",", ".")
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def get_primary_genre(genres_str: str) -> str:
    """Extract primary genre from comma-separated genres string."""
    if not genres_str:
        return ""
    parts = genres_str.split(",")
    return parts[0].strip() if parts else ""
