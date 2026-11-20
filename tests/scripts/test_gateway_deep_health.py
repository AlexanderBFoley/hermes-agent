"""scripts/gateway_deep_health.py: /v1/skills must be 200 with a non-empty list."""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "gateway_deep_health.py"
_spec = importlib.util.spec_from_file_location("gateway_deep_health", _SCRIPT)
deep_health = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(deep_health)


def _serve(skills_status: int, skills_body: dict):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/health":
                status, body = 200, {"status": "ok"}
            elif self.path == "/v1/skills":
                if self.headers.get("Authorization") != "Bearer k":
                    status, body = 401, {"error": "auth"}
                else:
                    status, body = skills_status, skills_body
            else:
                status, body = 404, {}
            payload = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"


@pytest.mark.parametrize(
    "status, body, ok",
    [
        (200, {"object": "list", "data": [{"name": "a"}]}, True),
        (200, {"object": "list", "data": []}, False),  # empty list is not healthy
        (500, {"error": {"message": "Failed to enumerate skills"}}, False),  # the HRM-1 regression
    ],
)
def test_deep_health_requires_nonempty_skills(status, body, ok):
    server, url = _serve(status, body)
    try:
        result = deep_health.check(url, "k", timeout=5)
    finally:
        server.shutdown()
    assert result["health_status"] == 200
    assert result["skills_status"] == status
    assert result["ok"] is ok


def test_deep_health_unreachable_gateway_fails():
    result = deep_health.check("http://127.0.0.1:9", "k", timeout=2)
    assert result["ok"] is False
    assert "error" in result
