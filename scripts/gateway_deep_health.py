#!/usr/bin/env python3
"""Deep health check for a running Hermes gateway API server.

``GET /health`` only proves the process answers. This probe also calls the authenticated
``GET /v1/skills`` and fails unless it returns 200 with a non-empty ``data`` list — the
regression where a stale ``include_editorial`` kwarg made every listing a 500 while
``/health`` stayed green.

Usage:
    python scripts/gateway_deep_health.py [--url http://127.0.0.1:8642] [--repeat 3]

The API key comes from ``API_SERVER_KEY`` or ``$HERMES_HOME/.env``; it is never printed.
Exit code 0 = every check passed on every round, 1 = any failure.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _api_key() -> str:
    key = os.environ.get("API_SERVER_KEY", "").strip()
    if key:
        return key
    home = os.environ.get("HERMES_HOME") or str(Path.home() / ".hermes")
    env_file = Path(home) / ".env"
    try:
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("API_SERVER_KEY="):
                return line.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def _get(url: str, key: str, timeout: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"} if key else {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def check(base: str, key: str, timeout: float = 15.0) -> dict:
    """One round: /health must be 200; /v1/skills must be 200 with a non-empty list."""
    result: dict = {"ok": False}
    try:
        status, _ = _get(f"{base}/health", key, timeout)
        result["health_status"] = status
        status, body = _get(f"{base}/v1/skills", key, timeout)
        result["skills_status"] = status
        if status == 200:
            data = json.loads(body).get("data")
            result["skills_count"] = len(data) if isinstance(data, list) else None
        else:
            result["skills_error"] = body[:200].decode("utf-8", "replace")
    except (OSError, ValueError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result
    result["ok"] = (result["health_status"] == 200 and result["skills_status"] == 200
                    and bool(result.get("skills_count")))
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=os.environ.get("HERMES_GATEWAY_URL", "http://127.0.0.1:8642"))
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--timeout", type=float, default=15.0)
    args = parser.parse_args(argv)
    key = _api_key()
    rounds = [check(args.url.rstrip("/"), key, args.timeout) for _ in range(max(1, args.repeat))]
    ok = all(r["ok"] for r in rounds)
    print(json.dumps({"ok": ok, "url": args.url, "rounds": rounds}))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
