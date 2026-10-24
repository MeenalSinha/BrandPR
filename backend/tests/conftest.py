import io
import os
import tempfile
from datetime import date, timedelta

# Environment must be set before the application modules are imported.
os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://brandpr:brandpr_dev_password@localhost:5432/brandpr_test"
)
os.environ["STORAGE_DIR"] = tempfile.mkdtemp(prefix="brandpr-test-storage-")
os.environ["MAX_UPLOAD_BYTES"] = str(1024 * 1024)
os.environ["CORS_ORIGINS"] = "http://localhost:3000,http://127.0.0.1:3000"
os.environ["REVIEW_WARNING_DAYS"] = "30"
os.environ["MAX_CONTENT_CHARS"] = "5000"
os.environ["LLM_API_KEY"] = ""  # tests never reach a real provider; they inject FakeProvider

import pymupdf  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

from app.main import create_app  # noqa: E402

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLES = "fact_change_impact_resolutions, risk_overrides, revision_corrections, workflow_events, content_assets, fact_change_impact_findings, fact_change_impacts, finding_evidence, review_findings, review_runs, content_submissions, fact_revisions, approved_facts, document_sections, source_documents, brands"


def alembic_config() -> Config:
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    return cfg


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()
    command.upgrade(alembic_config(), "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    import shutil
    from pathlib import Path

    for child in Path(os.environ["STORAGE_DIR"]).iterdir():
        shutil.rmtree(child) if child.is_dir() else child.unlink()
    engine = create_engine(os.environ["DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    engine.dispose()


@pytest.fixture
def client():
    with TestClient(create_app(), raise_server_exceptions=False) as c:
        yield c


def make_pdf(pages: list[str]) -> bytes:
    doc = pymupdf.open()
    for text_ in pages:
        page = doc.new_page()
        page.insert_textbox(pymupdf.Rect(54, 54, 540, 780), text_, fontsize=11, fontname="helv")
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture
def pdf_bytes():
    return make_pdf([
        "Product overview. Product name: Nova.",
        "Battery life: up to 18 hours under specified test conditions.",
        "Performance improvement: 25 percent under the approved comparison methodology.",
    ])


@pytest.fixture
def brand(client):
    r = client.post("/api/brands", json={"name": "Nova Systems", "description": "Fictional"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def other_brand(client):
    return client.post("/api/brands", json={"name": "Other Brand"}).json()


def upload(client, brand_id, name, data, mime="application/octet-stream", title=None):
    form = {"title": title} if title else None
    return client.post(f"/api/brands/{brand_id}/documents", files={"file": (name, io.BytesIO(data), mime)}, data=form)


@pytest.fixture
def pdf_doc(client, brand, pdf_bytes):
    r = upload(client, brand["id"], "spec.pdf", pdf_bytes, "application/pdf", title="Spec")
    assert r.status_code == 201 and r.json()["processing_status"] == "processed", r.text
    return r.json()


def fact_payload(**overrides):
    base = {
        "name": "Battery life", "value": "Up to 18 hours", "category": "product_spec",
        "qualifications": "Under specified test conditions", "owner": "Product team",
        "source_note": "Confirmed by the product team",
    }
    base.update(overrides)
    return base


@pytest.fixture
def fixed_today(monkeypatch):
    from app.core import clock

    day = date(2026, 10, 22)
    monkeypatch.setattr(clock, "today", lambda: day)
    return day


def days(n: int, base: date = date(2026, 10, 22)) -> str:
    return (base + timedelta(days=n)).isoformat()
