"""Direct Pinterest API publish helpers."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, Dict
from urllib.parse import urlparse

import requests

from kinopois.config import config


class PinterestPublishError(RuntimeError):
    """Raised when Pinterest publish fails."""


def _resolve_local_image_path(job: Dict[str, Any]) -> Path | None:
    image_url = str(job.get("image_url") or "").strip()
    if not image_url:
        return None

    path = urlparse(image_url).path
    filename = Path(path).name
    if not filename:
        return None

    for directory in (config.framed_posters_dir, config.posters_dir, config.framed_source_posters_dir):
        candidate = Path(directory) / filename
        if candidate.exists():
            return candidate
    return None


def publish_pin(job: Dict[str, Any]) -> str:
    """Publish one pin to Pinterest via REST API and return pin id."""
    token = (config.pinterest_access_token or "").strip()
    board_id = str(job.get("board_id") or config.pinterest_board_id or "").strip()

    if not token:
        raise PinterestPublishError("PINTEREST_ACCESS_TOKEN is not configured")
    if not board_id:
        raise PinterestPublishError("board_id is empty and PINTEREST_BOARD_ID fallback is not configured")

    image_url = str(job.get("image_url") or "").strip()
    title = str(job.get("title") or "").strip()
    description = str(job.get("description") or "").strip()
    link = str(job.get("link") or config.bot_url or "").strip()

    if not image_url:
        raise PinterestPublishError("image_url is empty")
    if not title:
        raise PinterestPublishError("title is empty")

    media_source: Dict[str, Any]
    local_image = _resolve_local_image_path(job)
    if local_image:
        raw = local_image.read_bytes()
        media_source = {
            "source_type": "image_base64",
            "content_type": "image/jpeg",
            "data": base64.b64encode(raw).decode("ascii"),
        }
    else:
        media_source = {
            "source_type": "image_url",
            "url": image_url,
        }

    payload = {
        "board_id": board_id,
        "title": title[:100],
        "description": description[:800],
        "media_source": media_source,
    }
    if link:
        payload["link"] = link

    response = requests.post(
        "https://api.pinterest.com/v5/pins",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )

    if response.status_code >= 300:
        detail = response.text[:1000]
        raise PinterestPublishError(f"Pinterest API {response.status_code}: {detail}")

    data = response.json() if response.content else {}
    pin_id = str(data.get("id") or "").strip()
    if not pin_id:
        raise PinterestPublishError("Pinterest response does not contain pin id")

    return pin_id
