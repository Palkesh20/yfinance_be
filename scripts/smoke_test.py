"""Hit /health through the ASGI app, or through SMOKE_BASE_URL when the API is already running."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend" / "src"))


def main() -> int:
    """Return 0 when the health route reports status ok."""
    base_url = os.environ.get("SMOKE_BASE_URL", "").strip()
    if base_url:
        response = httpx.get(f"{base_url.rstrip('/')}/health", timeout=10.0)
        payload = response.json()
        if response.status_code != 200 or payload.get("status") != "ok":
            print(f"health check failed: {response.status_code} {payload}", file=sys.stderr)
            return 1
        print("health check ok")
        return 0

    os.environ.setdefault("APP_ENV", "test")
    os.environ["SETTINGS_ENV_FILE"] = ""
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    from fastapi.testclient import TestClient

    from finance_poc.core.config import get_settings
    from finance_poc.main import create_app

    get_settings.cache_clear()
    with TestClient(create_app()) as client:
        response = client.get("/health")
    payload = response.json()
    if response.status_code != 200 or payload.get("status") != "ok":
        print(f"health check failed: {response.status_code} {payload}", file=sys.stderr)
        return 1
    print("health check ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
