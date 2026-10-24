import uuid
from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentActor
from app.core.auth import DEMO_USERS, authenticate_user, create_access_token
from app.core.errors import Unauthorized
from app.schemas.common import ERROR_RESPONSES

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str | None = None
    password: str | None = None
    demo_role: Literal["creator", "reviewer", "unauthorized"] | None = None


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


@router.post("/login", response_model=TokenResponse, summary="Sign in and receive verified JWT")
def login(data: LoginRequest) -> TokenResponse:
    user = authenticate_user(email=data.email or "", password=data.password, demo_role=data.demo_role)
    if not user:
        raise Unauthorized("Invalid credentials or unknown demo account.", code="invalid_credentials")

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
    }
