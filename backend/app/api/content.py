import uuid

from fastapi import APIRouter, Depends, status

from app.api.deps import DbSession, Limit, Offset, get_review_provider
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.review import ContentCreate, ContentRead, ContentSummary, ReviewCreate, ReviewRunRead
from app.services import content as svc
from app.services.review import pipeline

router = APIRouter(tags=["content"])


@router.post("/brands/{brand_id}/content", response_model=ContentRead, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES, summary="Submit marketing content")
def create_content(brand_id: uuid.UUID, data: ContentCreate, db: DbSession):
    return svc.content_read(db, svc.create_content(db, brand_id, data))


@router.get("/brands/{brand_id}/content", response_model=Page[ContentSummary], responses=ERROR_RESPONSES, summary="List submitted content for a brand", description="Every revision is listed; pass latest_only=true for one row per content asset (its newest revision).")
def list_content(brand_id: uuid.UUID, db: DbSession, limit: Limit = 50, offset: Offset = 0, latest_only: bool = False):
    items, total = svc.list_content(db, brand_id, limit, offset, latest_only=latest_only)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/content/{content_id}", response_model=ContentRead, responses=ERROR_RESPONSES, summary="Get submitted content with its saved text")
def get_content(content_id: uuid.UUID, db: DbSession):
    return svc.content_read(db, svc.get_content(db, content_id))


@router.post(
    "/content/{content_id}/reviews", response_model=ReviewRunRead, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES,
    summary="Run a review of the content",
    description="Runs synchronously and records a new review run every time. The response is 201 even when the run's `status` is `failed`: "
                "always check `status`. `completed_limited` means only deterministic rules ran (no AI provider configured).",
)
def create_review(content_id: uuid.UUID, db: DbSession, provider=Depends(get_review_provider), data: ReviewCreate | None = None):
    content = svc.get_content(db, content_id)
    run = pipeline.run_review(db, content, provider, data.requested_by if data else None)
    return svc.run_read(db, run, include_findings=True)


@router.get("/content/{content_id}/reviews", response_model=list[ReviewRunRead], responses=ERROR_RESPONSES, summary="Review history for content, newest first")
def list_reviews(content_id: uuid.UUID, db: DbSession):
    return svc.list_runs(db, content_id)
