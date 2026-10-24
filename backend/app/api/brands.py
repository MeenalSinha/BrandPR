import uuid

from fastapi import APIRouter, status

from app.api.deps import DbSession, Limit, Offset, OptionalActor, verify_brand_access
from app.schemas.brand import BrandCreate, BrandRead, BrandUpdate
from app.schemas.common import ERROR_RESPONSES, Page
from app.services import brands as svc

router = APIRouter(prefix="/brands", tags=["brands"])


@router.get("", response_model=Page[BrandRead], summary="List brands")
def list_brands(db: DbSession, limit: Limit = 50, offset: Offset = 0):
    rows, total = svc.list_brands(db, limit, offset)
    return Page(items=[BrandRead.model_validate(r) for r in rows], total=total, limit=limit, offset=offset)


@router.post("", response_model=BrandRead, status_code=status.HTTP_201_CREATED, responses=ERROR_RESPONSES, summary="Create a brand")
def create_brand(data: BrandCreate, db: DbSession):
    return svc.create_brand(db, data)


@router.get("/{brand_id}", response_model=BrandRead, responses=ERROR_RESPONSES, summary="Get a brand")
def get_brand(brand_id: uuid.UUID, db: DbSession, actor: OptionalActor = None):
    verify_brand_access(brand_id, actor)
    return svc.get_brand(db, brand_id)


@router.patch("/{brand_id}", response_model=BrandRead, responses=ERROR_RESPONSES, summary="Update a brand")
def update_brand(brand_id: uuid.UUID, data: BrandUpdate, db: DbSession, actor: OptionalActor = None):
    verify_brand_access(brand_id, actor)
    return svc.update_brand(db, brand_id, data)
