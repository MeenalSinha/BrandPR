import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status

from app.api.deps import DbSession, Limit, Offset, OptionalActor, verify_brand_access
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.fact import (
    EffectiveState, FactCategory, FactCreate, FactRead, FactRevisionRead, FactStatus, FactStatusUpdate, FactSummary,
    FactUpdate, ReviewState,
)
from app.services import facts as svc

router = APIRouter(tags=["facts"])


@router.get("/brands/{brand_id}/facts", response_model=Page[FactRead], responses=ERROR_RESPONSES, summary="List approved facts for a brand")
def list_facts(
    brand_id: uuid.UUID, db: DbSession, limit: Limit = 50, offset: Offset = 0,
    status: Annotated[FactStatus | None, Query(description="Approval status")] = None,
    category: FactCategory | None = None,
    effective_state: Annotated[EffectiveState | None, Query(description="Status combined with validity dates, evaluated today")] = None,
    review_state: ReviewState | None = None,
    review_within_days: Annotated[int | None, Query(ge=0, le=3650, description="Facts whose review date is on or before today + N days (includes overdue)")] = None,
    source_document_id: uuid.UUID | None = None,
    q: Annotated[str | None, Query(max_length=200, description="Search name, value, qualifications and owner")] = None,
    sort: Literal["updated_at", "name", "review_date", "expires_at", "created_at"] = "updated_at",
    actor: OptionalActor = None,
):
    verify_brand_access(brand_id, actor)
    rows, total = svc.list_facts(
        db, brand_id, limit=limit, offset=offset, status=status, category=category, effective=effective_state,
        review=review_state, review_within_days=review_within_days, source_document_id=source_document_id, q=q, sort=sort,
    )
    return Page(items=svc.to_read_many(db, rows), total=total, limit=limit, offset=offset)


@router.get("/brands/{brand_id}/facts/summary", response_model=FactSummary, responses=ERROR_RESPONSES, summary="Counts by effective and review state")
def facts_summary(brand_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    verify_brand_access(brand_id, actor)
    return svc.summary(db, brand_id)


@router.post("/brands/{brand_id}/facts", response_model=FactRead, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES, summary="Create a fact")
def create_fact(brand_id: uuid.UUID, data: FactCreate, db: DbSession, actor: OptionalActor = None):
    verify_brand_access(brand_id, actor)
    return svc.to_read(db, svc.create_fact(db, brand_id, data))


@router.get("/facts/{fact_id}", response_model=FactRead, responses=ERROR_RESPONSES, summary="Get a fact with its source")
def get_fact(fact_id: uuid.UUID, db: DbSession):
    return svc.to_read(db, svc.get_fact(db, fact_id))


@router.patch("/facts/{fact_id}", response_model=FactRead, responses=ERROR_RESPONSES, summary="Edit a fact",
              description="Editing wording, value, qualifications, unit, category or source of an active fact returns it to 'proposed' for re-approval.")
def update_fact(fact_id: uuid.UUID, data: FactUpdate, db: DbSession):
    return svc.to_read(db, svc.update_fact(db, fact_id, data))


@router.patch("/facts/{fact_id}/status", response_model=FactRead, responses=ERROR_RESPONSES, summary="Change a fact's approval status")
def update_status(fact_id: uuid.UUID, data: FactStatusUpdate, db: DbSession):
    return svc.to_read(db, svc.change_status(db, fact_id, data))


@router.get("/facts/{fact_id}/revisions", response_model=list[FactRevisionRead], responses=ERROR_RESPONSES, summary="Change history for a fact")
def revisions(fact_id: uuid.UUID, db: DbSession):
    return svc.list_revisions(db, fact_id)
