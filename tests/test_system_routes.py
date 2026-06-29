from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from server import Handler
from tests.test_system_schema import valid_config


def _request(base: str, method: str, path: str, body: dict[str, Any] | None = None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=3) as response:
        return response.status, json.loads(response.read())["data"]


def test_parameterized_system_and_record_routes(systems_db: Path) -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, data = _request(
            base,
            "POST",
            "/api/systems",
            {"config": valid_config(), "source_prompt": "Move abroad"},
        )
        assert status == 201
        system = data["system"]

        _, detail = _request(base, "GET", f"/api/systems/{system['id']}")
        entity_id = detail["system"]["entities"][0]["id"]
        assert detail["system"]["system_name"] == "Career Move"

        status, created = _request(
            base,
            "POST",
            f"/api/entities/{entity_id}/records",
            {"values": {"company": "Acme", "status": "applied"}},
        )
        assert status == 201
        record_id = created["record"]["id"]

        _, updated = _request(
            base,
            "PATCH",
            f"/api/records/{record_id}",
            {"values": {"status": "offer"}},
        )
        assert updated["record"]["values"]["status"] == "offer"

        _, records = _request(base, "GET", f"/api/entities/{entity_id}/records")
        assert records["records"][0]["values"]["company"] == "Acme"

        _, deleted = _request(base, "DELETE", f"/api/records/{record_id}")
        assert deleted["deleted"] is True
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
