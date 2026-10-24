import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError
from app.models import Brand
from app.schemas.brand import BrandCreate, BrandUpdate


def get_brand(db: Session, brand_id: uuid.UUID) -> Brand:
    brand = db.get(Brand, brand_id)
    if brand is None:
        raise NotFoundError("Brand not found.")
    return brand


def _ensure_name_free(db: Session, name: str, exclude: uuid.UUID | None = None) -> None:
    stmt = select(Brand.id).where(func.lower(Brand.name) == name.lower())
    if exclude:
        stmt = stmt.where(Brand.id != exclude)
    if db.scalar(stmt) is not None:
        raise ConflictError("A brand with this name already exists.", code="duplicate_brand")


def list_brands(db: Session, limit: int, offset: int) -> tuple[list[Brand], int]:
    total = db.scalar(select(func.count()).select_from(Brand)) or 0
    rows = db.scalars(select(Brand).order_by(Brand.name, Brand.id).limit(limit).offset(offset)).all()
    return list(rows), total


def create_brand(db: Session, data: BrandCreate) -> Brand:
    _ensure_name_free(db, data.name)
    brand = Brand(name=data.name, description=data.description)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def update_brand(db: Session, brand_id: uuid.UUID, data: BrandUpdate) -> Brand:
    brand = get_brand(db, brand_id)
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is not None:
        _ensure_name_free(db, changes["name"], exclude=brand.id)
        brand.name = changes["name"]
    if "description" in changes:
        brand.description = changes["description"]
    db.commit()
    db.refresh(brand)
    return brand
