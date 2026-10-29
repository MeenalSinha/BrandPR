import uuid
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import CurrentActor, DbSession, ReviewerActor, verify_brand_access
from app.core.auth import (
    DEMO_USERS,
    authenticate_user,
    create_access_token,
    hash_password,
    verify_oidc_token,
)
from app.core.errors import ConflictError, Forbidden, NotFoundError, Unauthorized, ValidationFailed
from app.models.user import BrandMembership, MembershipAuditLog, User
from app.schemas.common import ERROR_RESPONSES

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    demo_role: Literal["creator", "reviewer", "unauthorized"] | None = None


class RegisterRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=6, max_length=100)
    brand_id: uuid.UUID | None = None
    role: Literal["creator", "reviewer", "admin"] = "creator"


class OidcExchangeRequest(BaseModel):
    id_token: str = Field(description="Managed Identity / Google / Firebase issued ID Token")
    brand_id: uuid.UUID | None = None


class UserProfile(BaseModel):
    id: str
    name: str
    email: str
    role: str
    brand_ids: list[str] = Field(default_factory=lambda: ["*"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserProfile


class MembershipCreate(BaseModel):
    user_email: str
    role: Literal["creator", "reviewer", "admin"] = "creator"


class MembershipRead(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    brand_id: uuid.UUID
    email: str
    name: str
    role: str


@router.post("/login", response_model=TokenResponse, summary="Sign in and receive verified JWT")
def login(data: LoginRequest, db: DbSession) -> TokenResponse:
    user = authenticate_user(email=data.email or "", password=data.password, demo_role=data.demo_role, db=db)
    if not user:
        raise Unauthorized("Invalid credentials or unknown account.", code="invalid_credentials")

    token = create_access_token(
        {
            "sub": user["id"],
            "name": user["name"],
            "email": user["email"],
            "role": user["role"],
            "brand_ids": user.get("brand_ids", ["*"]),
        }
    )
    return TokenResponse(
        access_token=token,
        user=UserProfile(
            id=user["id"],
            name=user["name"],
            email=user["email"],
            role=user["role"],
            brand_ids=user.get("brand_ids", ["*"]),
        ),
    )


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED, summary="Register a new user")
def register(data: RegisterRequest, db: DbSession) -> TokenResponse:
    email_norm = data.email.strip().lower()
    existing = db.scalar(select(User).where(User.email == email_norm))
    if existing:
        raise ConflictError(f"User with email '{email_norm}' already exists.", code="user_already_exists")

    hashed = hash_password(data.password)
    new_user = User(
        email=email_norm,
        name=data.name.strip(),
        hashed_password=hashed,
        auth_provider="local",
        is_active=True,
    )
    db.add(new_user)
    db.flush()

    # Public self-registration always assigns creator role to prevent privilege escalation
    assigned_role = "creator"
    brand_ids = ["*"]
    if data.brand_id:
        membership = BrandMembership(user_id=new_user.id, brand_id=data.brand_id, role=assigned_role)
        db.add(membership)
        brand_ids = [str(data.brand_id)]

    db.commit()
    db.refresh(new_user)

    token = create_access_token(
        {
            "sub": str(new_user.id),
            "name": new_user.name,
            "email": new_user.email,
            "role": assigned_role,
            "brand_ids": brand_ids,
        }
    )
    return TokenResponse(
        access_token=token,
        user=UserProfile(
            id=str(new_user.id),
            name=new_user.name,
            email=new_user.email,
            role=assigned_role,
            brand_ids=brand_ids,
        ),
    )


@router.post("/oidc/exchange", response_model=TokenResponse, summary="Exchange an OIDC/Google ID token for an application JWT")
def exchange_oidc(data: OidcExchangeRequest, db: DbSession) -> TokenResponse:
    try:
        claims = verify_oidc_token(data.id_token)
    except Exception as e:
        raise Unauthorized(f"OIDC token verification failed: {e}", code="invalid_oidc_token")

    email = claims.get("email") or f"oidc_{claims.get('sub')}@external.internal"
    name = claims.get("name") or claims.get("email") or "OIDC User"
    provider_uid = claims.get("sub")

    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            email=email,
            name=name,
            auth_provider="oidc",
            provider_uid=provider_uid,
            is_active=True,
        )
        db.add(user)
        db.flush()
        if data.brand_id:
            membership = BrandMembership(user_id=user.id, brand_id=data.brand_id, role="creator")
            db.add(membership)
        db.commit()
        db.refresh(user)

    memberships = db.scalars(select(BrandMembership).where(BrandMembership.user_id == user.id)).all()
    role = "creator"
    brand_ids: list[str] = []
    for m in memberships:
        brand_ids.append(str(m.brand_id))
        if m.role in ("reviewer", "admin"):
            role = m.role

    token = create_access_token(
        {
            "sub": str(user.id),
            "name": user.name,
            "email": user.email,
            "role": role,
            "brand_ids": brand_ids or ["*"],
        }
    )
    return TokenResponse(
        access_token=token,
        user=UserProfile(
            id=str(user.id),
            name=user.name,
            email=user.email,
            role=role,
            brand_ids=brand_ids or ["*"],
        ),
    )


@router.post("/logout", summary="Sign out and invalidate local session")
def logout():
    return {"message": "Session invalidated successfully."}


@router.get("/demo-users", summary="List available verified demonstration accounts")
def demo_users():
    """Returns available demonstration accounts with valid, pre-signed tokens for easy role switching."""
    accounts = []
    for u in DEMO_USERS.values():
        token = create_access_token(
            {
                "sub": u["id"],
                "name": u["name"],
                "email": u["email"],
                "role": u["role"],
                "brand_ids": u.get("brand_ids", ["*"]),
            }
        )
        accounts.append(
            {
                "id": u["id"],
                "name": u["name"],
                "email": u["email"],
                "role": u["role"],
                "brand_ids": u.get("brand_ids", ["*"]),
                "access_token": token,
            }
        )
    return {"users": accounts}


@router.get("/me", summary="Get currently authenticated actor profile")
def me(actor: CurrentActor):
    return {
        "name": actor.name,
        "role": actor.role,
        "email": actor.email,
        "user_id": actor.user_id,
        "brand_ids": list(actor.brand_ids),
        "is_reviewer": actor.is_reviewer,
        "is_creator": actor.is_creator,
        "is_admin": actor.is_admin,
    }
