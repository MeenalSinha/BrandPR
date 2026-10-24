import uuid
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DbSession, Limit, Offset
from app.schemas.common import ERROR_RESPONSES, Page
from app.schemas.review import FindingRead, FindingStatus, ReviewRunRead
from app.services import content as svc

router = APIRouter(tags=["reviews"])


@router.get("/reviews/{review_id}", response_model=ReviewRunRead, responses=ERROR_RESPONSES, summary="Get a review run with finding counts")
def get_review(review_id: uuid.UUID, db: DbSession):
    return svc.run_read(db, svc.get_run(db, review_id))


@router.get("/reviews/{review_id}/findings", response_model=Page[FindingRead], responses=ERROR_RESPONSES, summary="Findings of a review, with their evidence")
def list_findings(review_id: uuid.UUID, db: DbSession, status: Annotated[FindingStatus | None, Query()] = None, limit: Limit = 200, offset: Offset = 0):
    items, total = svc.list_findings(db, review_id, status=status, limit=limit, offset=offset)
    return Page(items=items, total=total, limit=limit, offset=offset)
