"""HTTP server entry point.

Routing and transport only — all business logic lives in api/handlers.py.
"""
from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from api import handlers

_STATIC = Path(__file__).resolve().parent / "static"

_MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css",
    ".js": "application/javascript",
    ".json": "application/json",
    ".ico": "image/x-icon",
}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:  # noqa: ARG002
        pass

    # ── Transport helpers ──────────────────────────────────────────────────

    def _send_json(self, data: Any, status: int = 200) -> None:
        envelope = {"ok": status < 400, "data": data}
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, message: str, status: int = 400) -> None:
        code_map = {
            400: "BAD_REQUEST",
            404: "NOT_FOUND",
            409: "CONFLICT",
            500: "INTERNAL_ERROR",
            502: "LLM_UNAVAILABLE",
            504: "LLM_TIMEOUT",
        }
        envelope = {
            "ok": False,
            "error": {
                "code": code_map.get(status, "ERROR"),
                "message": message,
            },
        }
        body = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    _MAX_BODY = 4 * 1024 * 1024  # 4 MB

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", 0))
        if length > self._MAX_BODY:
            raise ValueError(f"Request body too large: {length} bytes (max {self._MAX_BODY})")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8"))

    def _serve_static(self, path: str) -> None:
        if path in ("/", ""):
            path = "/index.html"
        file_path = _STATIC / path.lstrip("/")
        if not file_path.exists() or not file_path.is_file():
            self.send_response(404)
            self.end_headers()
            return
        mime = _MIME.get(file_path.suffix, "application/octet-stream")
        content = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    # ── Routing ────────────────────────────────────────────────────────────

    def do_GET(self) -> None:
        path = self.path.split("?")[0]
        send, error = self._send_json, self._send_error
        if path == "/api/health":
            handlers.handle_health(send, error)
        elif path == "/api/config":
            handlers.handle_get_config(send, error)
        elif path == "/api/index":
            handlers.handle_get_index(send, error)
        elif path == "/api/habits":
            handlers.handle_get_habits(send, error)
        else:
            self._serve_static(path)

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        send, error = self._send_json, self._send_error
        body = self._read_body()
        routes = {
            "/api/config":       lambda: handlers.handle_post_config(body, send, error),
            "/api/scan":         lambda: handlers.handle_scan(send, error),
            "/api/aggregate":    lambda: handlers.handle_aggregate(body, send, error),
            "/api/preview":      lambda: handlers.handle_preview(body, send, error),
            "/api/write":        lambda: handlers.handle_write(body, send, error),
            "/api/tasks/toggle": lambda: handlers.handle_toggle_task(body, send, error),
            "/api/habits/toggle":lambda: handlers.handle_habit_toggle(body, send, error),
        }
        fn = routes.get(path)
        if fn:
            fn()
        else:
            error("Not found", 404)


def main() -> None:
    port = int(os.environ.get("PORT", 8765))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Smart Notes Aggregator → {url}")
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
