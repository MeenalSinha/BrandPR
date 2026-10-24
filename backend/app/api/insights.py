import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Query

from app.api.deps import DbSession
from app.schemas.common import ERROR_RESPONSES
from app.schemas.guideline import GovernanceInsightsOut
from app.services import insights as svc_i

router = APIRouter(tags=["insights"])


@router.get(
    "/brands/{brand_id}/insights",
    response_model=GovernanceInsightsOut,
    responses=ERROR_RESPONSES,
    summary="Get Governance Intelligence metrics, recurring problem patterns, and evidence-backed recommendations",
)
def get_brand_governance_insights(
    brand_id: uuid.UUID,
    db: DbSession,
    period: Annotated[Literal["7d", "30d", "all"], Query(description="Time window for metrics aggregation")] = "all",
):
    return svc_i.get_governance_insights(db, brand_id, period=period)
