import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, Limit, Offset, OptionalActor, verify_brand_access
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.review import FindingRead, FindingStatus, ReviewRunRead
from app.services import content as svc

router = APIRouter(tags=["reviews"])


@router.get("/reviews/{review_id}", response_model=ReviewRunRead, responses=ERROR_RESPONSES, summary="Get a review run with finding counts")
def get_review(review_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    run = svc.get_run(db, review_id)
    verify_brand_access(run.brand_id, actor)
    return svc.run_read(db, run)


@router.get("/reviews/{review_id}/findings", response_model=Page[FindingRead], responses=ERROR_RESPONSES, summary="Findings of a review, with their evidence")
def list_findings(review_id: uuid.UUID, db: DbSession, status: Annotated[FindingStatus | None, Query()] = None, limit: Limit = 200, offset: Offset = 0, actor: OptionalActor = None):
    run = svc.get_run(db, review_id)
    verify_brand_access(run.brand_id, actor)
    items, total = svc.list_findings(db, review_id, status=status, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)
