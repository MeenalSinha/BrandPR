from dataclasses import dataclass
from typing import Annotated
import uuid

from fastapi import Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.auth import decode_access_token
from app.core.config import get_settings
from app.core.errors import ActorRequired, Forbidden, Unauthorized, ValidationFailed, field_error
from app.db.session import get_db

DbSession = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200, description="Page size")]
Offset = Annotated[int, Query(ge=0, description="Items to skip")]


def get_review_provider():
    """The configured model provider, or None (limited mode). Tests override this dependency with a fake."""
    from app.services.review.providers import build_provider

    return build_provider()


# --------------------------------------------------------------------- authenticated identity
ACTOR_ROLES = ("creator", "reviewer")


@dataclass(frozen=True)
class Actor:
    name: str
    role: str
    email: str = ""
    user_id: str = ""
    brand_ids: tuple[str, ...] = ("*",)

    @property
    def is_reviewer(self) -> bool:
        return self.role == "reviewer"

    @property
    def is_creator(self) -> bool:
        return self.role == "creator"

    def can_access_brand(self, brand_id: uuid.UUID | str) -> bool:
        if "*" in self.brand_ids:
            return True
        return str(brand_id) in self.brand_ids


def get_actor(
    authorization: Annotated[str | None, Header(description="Bearer token authentication.")] = None,
    x_actor_name: Annotated[str | None, Header(description="Legacy demo header (ignored when auth is enforced).")] = None,
    x_actor_role: Annotated[str | None, Header(description="Legacy demo header (ignored when auth is enforced).")] = None,
) -> Actor:
    """Extract authenticated actor identity.

    Priority:
    1. Cryptographically verified Authorization: Bearer <jwt> token.
    2. In production or when auth_enforced=True: STRICTLY refuses caller-supplied role headers.
    3. In local test/development fallback only: allows demo headers when no token is supplied.
    """
    settings = get_settings()

    # 1. Bearer token verification (Always trusted when valid)
    if authorization and authorization.strip().lower().startswith("bearer "):
        token = authorization.strip()[7:].strip()
        try:
            payload = decode_access_token(token, settings.jwt_secret)
            return Actor(
                name=payload.get("name", "Authenticated User"),
                role=payload.get("role", "creator"),
                email=payload.get("email", ""),
                user_id=payload.get("sub", ""),
                brand_ids=tuple(payload.get("brand_ids", ["*"])),
            )
        except Exception as e:
            raise Unauthorized(f"Invalid authentication token: {e}", code="invalid_token")

    # 2. Strict Production Guard: Do NOT rely on caller-supplied role headers
    if settings.app_env == "production" or settings.auth_enforced:
        raise Unauthorized("Authentication required. Send Authorization: Bearer <token>.", code="unauthorized")

    # 3. Development/Unit Test fallback
    name = (x_actor_name or "").strip()
    role = (x_actor_role or "").strip().lower()
    if not name or not role:
        raise ActorRequired("This action needs an actor. Send Authorization: Bearer <token> or demo identity headers.")
    if role not in ACTOR_ROLES:
        raise ValidationFailed("Unknown role.", details=[field_error("X-Actor-Role", "Must be 'creator' or 'reviewer'.")])
    if len(name) > 200:
        raise ValidationFailed("The actor name is too long.", details=[field_error("X-Actor-Name", "At most 200 characters.")])
    return Actor(name=name, role=role)


def require_reviewer(actor: Annotated[Actor, Depends(get_actor)]) -> Actor:
    if not actor.is_reviewer:
        raise Forbidden("Only a reviewer can do this.", code="reviewer_role_required")
    return actor


CurrentActor = Annotated[Actor, Depends(get_actor)]
ReviewerActor = Annotated[Actor, Depends(require_reviewer)]


def get_optional_actor(
    authorization: Annotated[str | None, Header()] = None,
    x_actor_name: Annotated[str | None, Header()] = None,
    x_actor_role: Annotated[str | None, Header()] = None,
) -> Actor | None:
    """For read endpoints: without valid identity the caller is anonymous."""
    if authorization or x_actor_name or x_actor_role:
        try:
            return get_actor(authorization, x_actor_name, x_actor_role)
        except (Unauthorized, ActorRequired, ValidationFailed):
            return None
    return None


OptionalActor = Annotated[Actor | None, Depends(get_optional_actor)]


def verify_brand_access(brand_id: uuid.UUID | str, actor: Actor | None) -> None:
    """Check that the actor has permission to access records for the given brand."""
    if actor is not None and not actor.can_access_brand(brand_id):
        raise Forbidden("You are not authorized to access records for this brand.", code="brand_access_denied")

