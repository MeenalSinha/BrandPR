"""File-type detection and text extraction for PDF, plain text and CSV.

Detection looks at file content, not just the filename or declared MIME type.
Extraction keeps locations: PDF page numbers, text line ranges, CSV headers with row numbers.
"""
import csv
import io
import re
from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

import pymupdf

from app.core.errors import UnsupportedMediaType, ValidationFailed

MIME_BY_TYPE = {"pdf": "application/pdf", "text": "text/plain", "csv": "text/csv"}
ALLOWED_EXTENSIONS = {".pdf": "pdf", ".txt": "text", ".csv": "csv"}
TEXT_BLOCK_TARGET = 1200
TEXT_BLOCK_MAX = 2000
CSV_ROWS_PER_SECTION = 50


class ExtractionFailed(Exception):
    """Raised when a validated file cannot be processed; message is safe to show to users."""


@dataclass
class SectionData:
    kind: str
    text: str
    page_number: int | None = None
    line_start: int | None = None
    line_end: int | None = None
    row_start: int | None = None
    row_end: int | None = None
    meta: dict[str, Any] | None = None


@dataclass
class ExtractionResult:
    sections: list[SectionData] = field(default_factory=list)
    page_count: int | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(s.text for s in self.sections if s.text)


def sanitize_filename(raw: str | None) -> str:
    """Display-only name: no directories, no control characters, bounded length."""
    name = (raw or "").strip()
    name = PureWindowsPath(PurePosixPath(name).name).name
    name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip(" .")
    return (name or "document")[:200]


def detect_type(filename: str, data: bytes) -> str:
    """Return 'pdf' | 'text' | 'csv' or raise UnsupportedMediaType / ValidationFailed."""
    if not data:
        raise ValidationFailed("The uploaded file is empty.")
    ext = PurePosixPath(filename.lower()).suffix
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedMediaType("Unsupported file type. Upload a PDF, plain text (.txt) or CSV file.")
    kind = ALLOWED_EXTENSIONS[ext]
    looks_pdf = data[:1024].lstrip().startswith(b"%PDF-")
    if kind == "pdf":
        if not looks_pdf:
            raise UnsupportedMediaType("The file has a .pdf extension but its content is not a PDF.")
        return kind
    if looks_pdf or b"\x00" in data[:8192] or data[:2] == b"MZ" or data[:4] == b"\x7fELF":
        raise UnsupportedMediaType(f"The file has a {ext} extension but its content is not plain text.")
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UnsupportedMediaType("Text and CSV files must be UTF-8 encoded.") from None
    return kind


def extract(kind: str, data: bytes, *, max_pdf_pages: int, max_csv_rows: int) -> ExtractionResult:
    if kind == "pdf":
        return _extract_pdf(data, max_pdf_pages)
    text = data.decode("utf-8-sig")
    if kind == "csv":
        return _extract_csv(text, max_csv_rows)
    return _extract_text(text)


def _extract_pdf(data: bytes, max_pages: int) -> ExtractionResult:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise ExtractionFailed("The PDF could not be opened. It may be corrupt or truncated.") from None
    try:
        if doc.needs_pass or doc.is_encrypted:
            raise ExtractionFailed("The PDF is password protected. Remove the password and upload it again.")
        if doc.page_count == 0:
            raise ExtractionFailed("The PDF contains no pages.")
        if doc.page_count > max_pages:
            raise ExtractionFailed(f"The PDF has {doc.page_count} pages; the limit is {max_pages}.")
        result = ExtractionResult(page_count=doc.page_count)
        for index in range(doc.page_count):
            try:
                text = doc[index].get_text("text").strip()
            except Exception:
                raise ExtractionFailed(f"Page {index + 1} could not be read. The PDF may be corrupt.") from None
            result.sections.append(SectionData(kind="page", text=text, page_number=index + 1))
        if not any(s.text for s in result.sections):
            raise ExtractionFailed(
                "No extractable text was found. The PDF may be a scan; OCR is not supported in this version."
            )
        return result
    finally:
        doc.close()


def _extract_text(text: str) -> ExtractionResult:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not text.strip():
        raise ExtractionFailed("The text file contains no readable text.")
    result = ExtractionResult()
    buf: list[str] = []
    start = 1
    size = 0

    def flush(end: int) -> None:
        nonlocal buf, size
        block = "\n".join(buf).strip()
        if block:
            result.sections.append(SectionData(kind="text_block", text=block, line_start=start, line_end=end))
        buf, size = [], 0

    for number, line in enumerate(lines, start=1):
        if not buf:
            start = number
        buf.append(line)
        size += len(line) + 1
        if size >= TEXT_BLOCK_MAX or (size >= TEXT_BLOCK_TARGET and not line.strip()):
            flush(number)
    if buf:
        flush(len(lines))
    return result


def _unique_headers(raw: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    headers = []
    for i, h in enumerate(raw, start=1):
        name = h.strip() or f"column_{i}"
        seen[name] = seen.get(name, 0) + 1
        headers.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    return headers


def _extract_csv(text: str, max_rows: int) -> ExtractionResult:
    try:
        reader = csv.reader(io.StringIO(text, newline=""))
        rows = [r for r in reader if any(c.strip() for c in r)]
    except csv.Error as exc:
        raise ExtractionFailed(f"The CSV could not be parsed: {exc}") from None
    if not rows:
        raise ExtractionFailed("The CSV file contains no rows.")
    headers = _unique_headers(rows[0])
    body = rows[1:]
    if not body:
        raise ExtractionFailed("The CSV file has a header row but no data rows.")
    if len(body) > max_rows:
        raise ExtractionFailed(f"The CSV has {len(body)} data rows; the limit is {max_rows}.")
    result = ExtractionResult()
    for batch_start in range(0, len(body), CSV_ROWS_PER_SECTION):
        batch = body[batch_start : batch_start + CSV_ROWS_PER_SECTION]
        row_dicts, lines = [], []
        for offset, row in enumerate(batch):
            number = batch_start + offset + 1
            cells = {}
            for i, value in enumerate(row):
                key = headers[i] if i < len(headers) else f"column_{i + 1}"
                cells[key] = value.strip()
            row_dicts.append({"row_number": number, "cells": cells})
            lines.append(f"Row {number}: " + "; ".join(f"{k} = {v}" for k, v in cells.items()))
        result.sections.append(
            SectionData(
                kind="csv_rows",
                text="\n".join(lines),
                row_start=batch_start + 1,
                row_end=batch_start + len(batch),
                meta={"headers": headers, "rows": row_dicts, "total_rows": len(body)},
            )
        )
    return result
