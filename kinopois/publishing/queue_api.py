"""Tiny HTTP API for the SQLite-backed publish queue."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict
from urllib.parse import parse_qs, urlparse

from kinopois.config import config
from kinopois.publishing.db import claim_ready_jobs, db_counts, mark_failed, mark_posted
from kinopois.publishing.eventlog import log_event


class _QueueAPIHandler(BaseHTTPRequestHandler):
    server_version = "kinopois-queue-api/1.0"

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return

    def _send_json(self, status: int, payload: Dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/healthz":
            self._send_json(200, {"status": "ok"})
            return
        if parsed.path == "/queue/next":
            query = parse_qs(parsed.query)
            limit = max(1, int((query.get("limit", ["1"])[0] or "1")))
            rows = claim_ready_jobs(limit=limit)
            if limit == 1:
                self._send_json(200, rows[0] if rows else {})
            else:
                self._send_json(200, {"items": rows, "count": len(rows)})
            return
        if parsed.path == "/queue/stats":
            self._send_json(200, db_counts())
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            payload = self._read_json()
        except Exception as exc:
            self._send_json(400, {"error": "invalid_json", "message": str(exc)})
            return

        if parsed.path == "/queue/posted":
            job_id = int(payload.get("job_id") or 0)
            pin_id = str(payload.get("pin_id") or "").strip()
            if not job_id or not pin_id:
                self._send_json(400, {"error": "missing_job_id_or_pin_id"})
                return
            mark_posted(job_id, pin_id)
            log_event("queue_api_mark_posted", job_id=job_id, pin_id=pin_id)
            self._send_json(200, {"ok": True, "job_id": job_id, "pin_id": pin_id})
            return

        if parsed.path == "/queue/failed":
            job_id = int(payload.get("job_id") or 0)
            error = str(payload.get("error") or payload.get("message") or "unknown error").strip()
            if not job_id:
                self._send_json(400, {"error": "missing_job_id"})
                return
            mark_failed(job_id, error)
            log_event("queue_api_mark_failed", job_id=job_id, error=error[:500])
            self._send_json(200, {"ok": True, "job_id": job_id, "error": error})
            return

        self._send_json(404, {"error": "not_found"})


def serve_queue_api(host: str | None = None, port: int | None = None) -> None:
    bind_host = host or config.queue_api_host
    bind_port = int(port or config.queue_api_port)
    httpd = ThreadingHTTPServer((bind_host, bind_port), _QueueAPIHandler)
    log_event("queue_api_started", host=bind_host, port=bind_port)
    print(f"Queue API listening on http://{bind_host}:{bind_port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        log_event("queue_api_stopped", host=bind_host, port=bind_port)
