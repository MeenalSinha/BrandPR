"""Phase 1 document-processing tests (P1-11 .. P1-18)."""
import hashlib
import os
from pathlib import Path

from tests.conftest import make_pdf, upload

STORAGE = Path(os.environ["STORAGE_DIR"])


def test_p1_11_valid_pdf_upload(client, brand, pdf_bytes):
    r = upload(client, brand["id"], "Nova Spec.pdf", pdf_bytes, "application/pdf")
    assert r.status_code == 201
    d = r.json()
    assert d["processing_status"] == "processed" and d["source_type"] == "pdf" and d["page_count"] == 3
    assert d["section_count"] == 3 and d["char_count"] > 0 and d["processed_at"] and d["error_message"] is None
    assert d["content_hash"] == hashlib.sha256(pdf_bytes).hexdigest() and d["title"] == "Nova Spec.pdf"
    assert "storage_path" not in d and str(STORAGE) not in r.text  # no server paths exposed


def test_p1_12_pdf_text_has_page_references(client, pdf_doc):
    sections = client.get(f"/api/documents/{pdf_doc['id']}/sections").json()["items"]
    assert [s["page_number"] for s in sections] == [1, 2, 3] and all(s["kind"] == "page" for s in sections)
    assert "Battery life: up to 18 hours" in sections[1]["text"]
    assert "Performance improvement" in sections[2]["text"]
    full = client.get(f"/api/documents/{pdf_doc['id']}/text").json()
    assert "Product name: Nova" in full["text"]
    assert client.get(f"/api/documents/{pdf_doc['id']}/file?inline=true").headers["content-disposition"].startswith("inline")


def test_p1_13_plain_text_upload(client, brand):
    body = "First paragraph about Nova.\n\nSecond paragraph about battery life.\nStill second.\n"
    r = upload(client, brand["id"], "notes.txt", body.encode(), "text/plain")
    assert r.status_code == 201 and r.json()["processing_status"] == "processed" and r.json()["source_type"] == "text"
    sec = client.get(f"/api/documents/{r.json()['id']}/sections").json()["items"][0]
    assert sec["kind"] == "text_block" and sec["line_start"] == 1 and sec["line_end"] == 5 and "battery life" in sec["text"]
    assert client.get(f"/api/documents/{r.json()['id']}/text").json()["text"].startswith("First paragraph")


def test_p1_14_csv_headers_and_rows(client, brand):
    csv_text = "Specification,Value,Unit\nWeight,1.24,kg\nMemory,16,GB\n"
    r = upload(client, brand["id"], "spec.csv", csv_text.encode(), "text/csv")
    assert r.status_code == 201 and r.json()["processing_status"] == "processed" and r.json()["source_type"] == "csv"
    table = client.get(f"/api/documents/{r.json()['id']}/table").json()
    assert table["headers"] == ["Specification", "Value", "Unit"] and table["total_rows"] == 2
    assert table["rows"][1] == {"row_number": 2, "cells": {"Specification": "Memory", "Value": "16", "Unit": "GB"}}
    page = client.get(f"/api/documents/{r.json()['id']}/table?limit=1&offset=1").json()
    assert [row["row_number"] for row in page["rows"]] == [2]
    assert client.get(f"/api/documents/{r.json()['id']}/sections").json()["items"][0]["row_end"] == 2


def test_p1_15_corrupt_pdf_marked_failed_with_useful_error(client, brand):
    r = upload(client, brand["id"], "broken.pdf", b"%PDF-1.4\n1 0 obj << /Type /Catalog >>\ngarbage", "application/pdf")
    assert r.status_code == 201
    d = r.json()
    assert d["processing_status"] == "failed" and "PDF" in d["error_message"] and d["page_count"] is None
    assert d["section_count"] == 0 and d["processed_at"] is None
    assert client.get(f"/api/documents/{d['id']}/text").status_code == 409
    assert client.get(f"/api/documents/{d['id']}/file").status_code == 404  # failed file is not retained
    assert not list(STORAGE.rglob(f"{d['id']}*"))
    # A failed record can never be cited as a source.
    f = client.post(f"/api/brands/{brand['id']}/facts", json={"name": "x", "value": "y", "source_document_id": d["id"]})
    assert f.status_code == 422 and "not been processed" in f.json()["error"]["details"][0]["message"]
    # Re-uploading the same bytes is allowed after a failure.
    assert upload(client, brand["id"], "broken.pdf", b"%PDF-1.4\n1 0 obj << /Type /Catalog >>\ngarbage").status_code == 201


def test_p1_15b_empty_and_scanned_style_pdfs_fail_honestly(client, brand):
    blank = make_pdf([""])
    r = upload(client, brand["id"], "blank.pdf", blank)
    assert r.json()["processing_status"] == "failed" and "No extractable text" in r.json()["error_message"]
    bad_csv = upload(client, brand["id"], "headers.csv", b"a,b,c\n")
    assert bad_csv.json()["processing_status"] == "failed" and "no data rows" in bad_csv.json()["error_message"]


def test_p1_16_unsupported_or_disguised_files_rejected(client, brand, pdf_bytes):
    cases = [
        ("tool.exe", b"MZ\x90\x00 binary"), ("image.png", b"\x89PNG\r\n\x1a\n"), ("noext", b"hello"),
        ("renamed.pdf", b"just text pretending"), ("disguised.txt", pdf_bytes), ("binary.csv", b"a,b\x00\x01\n1,2"),
        ("latin1.txt", "caf\xe9".encode("latin-1")), ("macro.docx", b"PK\x03\x04"), ("../../etc/passwd.sh", b"#!/bin/sh"),
    ]
    for name, data in cases:
        r = upload(client, brand["id"], name, data, "application/pdf")
        assert r.status_code == 415, (name, r.status_code, r.text)
        assert r.json()["error"]["code"] == "unsupported_file_type"
    assert upload(client, brand["id"], "empty.txt", b"").status_code == 422
    assert client.get(f"/api/brands/{brand['id']}/documents").json()["total"] == 0
    assert not [p for p in STORAGE.rglob("*") if p.is_file()]


def test_p1_17_oversized_file_rejected(client, brand):
    limit = int(os.environ["MAX_UPLOAD_BYTES"])
    r = upload(client, brand["id"], "big.txt", b"a" * (limit + 1))
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"
    assert client.get(f"/api/brands/{brand['id']}/documents").json()["total"] == 0
    assert upload(client, brand["id"], "ok.txt", b"a" * limit).status_code == 201  # boundary is inclusive


def test_p1_18_duplicate_upload_policy(client, brand, other_brand, pdf_bytes):
    first = upload(client, brand["id"], "spec.pdf", pdf_bytes)
    assert first.status_code == 201
    second = upload(client, brand["id"], "renamed-copy.pdf", pdf_bytes)
    assert second.status_code == 409 and second.json()["error"]["code"] == "duplicate_document"
    assert first.json()["id"] in second.json()["error"]["details"][0]["message"]
    assert client.get(f"/api/brands/{brand['id']}/documents").json()["total"] == 1
    assert upload(client, other_brand["id"], "spec.pdf", pdf_bytes).status_code == 201  # per-brand policy
    client.post(f"/api/documents/{first.json()['id']}/archive")
    assert upload(client, brand["id"], "spec.pdf", pdf_bytes).status_code == 201  # archived copies do not block


def test_filename_is_never_used_as_a_path(client, brand):
    r = upload(client, brand["id"], "../../../tmp/evil.txt", b"safe content")
    assert r.status_code == 201 and r.json()["filename"] == "evil.txt"
    files = [p for p in STORAGE.rglob("*") if p.is_file()]
    assert len(files) == 1 and files[0].name == f"{r.json()['id']}.txt"
    assert str(STORAGE.resolve()) in str(files[0].resolve())


def test_download_is_attachment_with_safe_headers(client, brand):
    r = upload(client, brand["id"], "notes.txt", b"<script>alert(1)</script>", "text/html")
    d = r.json()
    dl = client.get(f"/api/documents/{d['id']}/file")
    assert dl.status_code == 200 and dl.content == b"<script>alert(1)</script>"
    assert dl.headers["content-disposition"].startswith("attachment")
    assert dl.headers["x-content-type-options"] == "nosniff" and dl.headers["content-type"].startswith("text/plain")
    assert "sandbox" in dl.headers["content-security-policy"]
    assert client.get(f"/api/documents/{d['id']}/file?inline=true").headers["content-disposition"].startswith("attachment")


def test_delete_unreferenced_document_removes_record_and_file(client, brand):
    d = upload(client, brand["id"], "notes.txt", b"hello world").json()
    assert any(STORAGE.rglob(f"{d['id']}*"))
    assert client.delete(f"/api/documents/{d['id']}").status_code == 204
    assert client.get(f"/api/documents/{d['id']}").status_code == 404
    assert not any(STORAGE.rglob(f"{d['id']}*"))


def test_table_view_only_for_csv(client, pdf_doc):
    assert client.get(f"/api/documents/{pdf_doc['id']}/table").status_code == 409


def test_upload_to_unknown_brand_404(client, pdf_bytes):
    assert upload(client, "00000000-0000-0000-0000-000000000000", "a.pdf", pdf_bytes).status_code == 404
