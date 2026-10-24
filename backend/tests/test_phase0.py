"""Phase 0 acceptance tests P0-01 .. P0-10."""
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

from app.core.config import Settings, get_settings
from tests.conftest import BACKEND_DIR

REPO = Path(BACKEND_DIR).parent
SKIP_DIRS = {".git", "node_modules", ".next", "storage", "venv", ".venv", "__pycache__", ".pytest_cache", "playwright-report"}


def test_p0_01_backend_starts_with_real_server():
    """P0-01: uvicorn boots the app from the environment and answers /api/health."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"],
        cwd=BACKEND_DIR, env=os.environ.copy(), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(50):
            try:
                r = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=1)
                break
            except httpx.TransportError:
                time.sleep(0.2)
        else:
            pytest.fail("server did not start: " + (proc.stdout.read(2000).decode() if proc.poll() is not None else "timeout"))
        assert r.status_code == 200 and r.json()["status"] == "ok"
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_p0_03_health_endpoint(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["service"] == "brandpr-api" and body["environment"] == "test"
    assert r.headers["x-request-id"]


def test_p0_04_database_connection(client):
    r = client.get("/api/health/db")
    assert r.status_code == 200
    assert r.json()["database"] == "connected" and r.json()["server_version"]


def test_p0_05_configuration_from_environment(monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "12345")
    monkeypatch.setenv("CORS_ORIGINS", "https://a.example, https://b.example")
    get_settings.cache_clear()
    try:
        s = get_settings()
        assert s.max_upload_bytes == 12345
        assert s.cors_origin_list == ["https://a.example", "https://b.example"]
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


def test_p0_05b_production_rejects_development_defaults():
    with pytest.raises(RuntimeError):
        Settings(app_env="production").assert_safe_for_environment()
    Settings(
        app_env="production", database_url="postgresql+psycopg://u:realpass@db/brandpr",
        cors_origins="https://brandpr.example.com",
    ).assert_safe_for_environment()


SECRET_PATTERNS = [
    r"sk-[A-Za-z0-9]{20,}", r"AKIA[0-9A-Z]{16}", r"ghp_[A-Za-z0-9]{30,}", r"xox[baprs]-[A-Za-z0-9-]{10,}",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----", r"AIza[0-9A-Za-z_-]{35}",
]


def _tracked_text_files():
    for path in REPO.rglob("*"):
        if path.is_file() and not (set(path.relative_to(REPO).parts) & SKIP_DIRS):
            if path.suffix.lower() in {".pdf", ".png", ".ico", ".zip", ".woff", ".woff2", ".exe"} or path.name == ".env":
                continue
            try:
                yield path, path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue


def test_p0_06_no_secrets_in_repository():
    hits = [
        f"{p.relative_to(REPO)}: {pat}" for p, text in _tracked_text_files() for pat in SECRET_PATTERNS if re.search(pat, text)
    ]
    assert not hits, hits


def test_p0_06b_env_example_and_gitignore():
    example = (REPO / ".env.example").read_text()
    for line in example.splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            if re.search(r"(KEY|SECRET|TOKEN)", key):
                assert value.strip() == "", f"{key} must be empty in .env.example"
            if key.startswith("NEXT_PUBLIC_"):
                assert not re.search(r"(KEY|SECRET|TOKEN|PASSWORD|DATABASE)", key), f"{key} would be exposed to browsers"
    assert "postgresql" in example
    ignore = (REPO / ".gitignore").read_text()
    for entry in (".env", "node_modules", "storage/", ".next"):
        assert entry in ignore, f".gitignore is missing {entry}"


def test_p0_07_invalid_request_returns_structured_error(client):
    r = client.post("/api/brands", json={"name": ""})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error" and err["details"][0]["field"] == "name" and err["request_id"]
    assert client.post("/api/brands", json={"name": "x", "bogus": 1}).status_code == 422
    assert client.get("/api/facts/not-a-uuid").json()["error"]["code"] == "validation_error"
    nf = client.get("/api/facts/00000000-0000-0000-0000-000000000000")
    assert nf.status_code == 404 and nf.json()["error"]["code"] == "not_found"


def test_p0_07b_errors_do_not_leak_internals(client, monkeypatch):
    from app.services import brands

    def boom(*a, **k):
        raise ValueError("secret /srv/path/leak")

    monkeypatch.setattr(brands, "list_brands", boom)
    r = client.get("/api/brands")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "leak" not in r.text and "Traceback" not in r.text


def test_p0_08_cors_allows_dev_origin_only(client):
    ok = client.options(
        "/api/brands", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"}
    )
    assert ok.status_code == 200 and ok.headers["access-control-allow-origin"] == "http://localhost:3000"
    simple = client.get("/api/health", headers={"Origin": "http://localhost:3000"})
    assert simple.headers["access-control-allow-origin"] == "http://localhost:3000"
    bad = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_p0_09_api_documentation_available(client):
    assert client.get("/api/docs").status_code == 200
    spec = client.get("/api/openapi.json").json()
    for path in ("/api/health", "/api/brands", "/api/brands/{brand_id}/facts", "/api/brands/{brand_id}/documents", "/api/facts/{fact_id}"):
        assert path in spec["paths"], path
    for schema in ("BrandRead", "DocumentRead", "FactRead", "ErrorResponse", "HealthResponse"):
        assert schema in spec["components"]["schemas"], schema


def test_p0_10_readme_documents_setup():
    readme = (REPO / "README.md").read_text()
    for needle in ("alembic upgrade head", "app.scripts.seed", "uvicorn app.main:app", "npm install", "npm run dev",
                   "pytest", ".env.example", "docker compose"):
        assert needle in readme, f"README is missing: {needle}"


def test_clock_offset_shifts_only_date_rules_and_is_refused_in_production(monkeypatch):
    from datetime import datetime, timezone

    from app.core import clock
    from app.core.config import Settings, get_settings

    real_today = clock.today()
    monkeypatch.setattr(get_settings(), "clock_offset_days", 10)
    assert (clock.today() - real_today).days == 10
    assert abs((clock.now() - datetime.now(timezone.utc)).total_seconds()) < 5      # timestamps are not shifted
    monkeypatch.undo()
    assert clock.today() == real_today
    with pytest.raises(RuntimeError, match="CLOCK_OFFSET_DAYS"):
        Settings(app_env="production", clock_offset_days=3, database_url="postgresql+psycopg://u:realsecret@db/x", cors_origins="https://app.example.com").assert_safe_for_environment()
