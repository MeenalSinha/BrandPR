import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, Limit, Offset
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.impact import ImpactDetail, ImpactRead, ImpactStatus, ImpactSummary, ImpactTrigger
from app.services import impacts as svc

router = APIRouter(tags=["fact-change-impacts"])

SWEEP_NOTE = (
    "Before answering, this request runs the on-demand expiry sweep for the brand: facts stored as 'active' whose expiry date "
    "has passed are checked for content that relied on them, and impacts are recorded once (repeated requests never duplicate them). "
    "This is not a background job; expiry impacts appear the first time the ledger is read after the expiry date."
)


@router.get("/brands/{brand_id}/fact-change-impacts", response_model=Page[ImpactRead], responses=ERROR_RESPONSES,
            summary="Content that needs another review because a fact changed or expired", description=SWEEP_NOTE)
def list_impacts(
    brand_id: uuid.UUID, db: DbSession, limit: Limit = 50, offset: Offset = 0,
    fact_id: Annotated[uuid.UUID | None, Query(description="Only impacts of this fact (must belong to the brand).")] = None,
    status: ImpactStatus | None = None, trigger_type: ImpactTrigger | None = None,
    content_id: Annotated[uuid.UUID | None, Query(description="Only impacts of this content item.")] = None,
):
    items, total = svc.list_impacts(db, brand_id, limit=limit, offset=offset, fact_id=fact_id, status=status, trigger_type=trigger_type, content_id=content_id)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/brands/{brand_id}/fact-change-impacts/summary", response_model=ImpactSummary, responses=ERROR_RESPONSES,
            summary="Counts of open impacts, computed from the stored records", description=SWEEP_NOTE)
def impacts_summary(brand_id: uuid.UUID, db: DbSession):
    return svc.summary(db, brand_id)


@router.get("/facts/{fact_id}/impacts", response_model=Page[ImpactRead], responses=ERROR_RESPONSES,
            summary="Impacts caused by one fact", description=SWEEP_NOTE)
def fact_impacts(fact_id: uuid.UUID, db: DbSession, limit: Limit = 50, offset: Offset = 0, status: ImpactStatus | None = None, trigger_type: ImpactTrigger | None = None):
    items, total = svc.list_for_fact(db, fact_id, limit=limit, offset=offset, status=status, trigger_type=trigger_type)
    return Page(items=items, total=total, limit=limit, offset=offset)


@router.get("/fact-change-impacts/{impact_id}", response_model=ImpactDetail, responses=ERROR_RESPONSES,
            summary="One impact with the historical findings and fact snapshots behind it")
def get_impact(impact_id: uuid.UUID, db: DbSession):
    return svc.get_impact(db, impact_id)
