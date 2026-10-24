import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

ProcessingStatus = Literal["pending", "processing", "processed", "failed"]
SourceType = Literal["pdf", "text", "csv"]
SectionKind = Literal["page", "text_block", "csv_rows"]


class DocumentRead(BaseModel):
    """Source document metadata. The storage location is deliberately not exposed."""

    id: uuid.UUID
    brand_id: uuid.UUID
    title: str
    filename: str
    mime_type: str
    size_bytes: int
    source_type: SourceType
    processing_status: ProcessingStatus
    content_hash: str
    page_count: int | None
    section_count: int
    char_count: int
    fact_count: int = Field(description="Number of approved facts that cite this document.")
    uploaded_at: datetime
    processed_at: datetime | None
    error_message: str | None
    archived_at: datetime | None


class SectionRead(BaseModel):
    id: uuid.UUID
    document_id: uuid.UUID
    section_index: int
    kind: SectionKind
    page_number: int | None
    line_start: int | None
    line_end: int | None
    row_start: int | None
    row_end: int | None
    text: str
    meta: dict[str, Any] | None


class DocumentTextRead(BaseModel):
    document_id: uuid.UUID
    title: str
    text: str


class TableRow(BaseModel):
    row_number: int
    cells: dict[str, str]


class TableRead(BaseModel):
    document_id: uuid.UUID
    headers: list[str]
    rows: list[TableRow]
    total_rows: int
    limit: int
    offset: int


class DocumentArchiveRequest(BaseModel):
    pass
