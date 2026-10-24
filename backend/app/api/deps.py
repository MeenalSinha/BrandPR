from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Query
from sqlalchemy.orm import Session

from app.core.errors import ActorRequired, Forbidden, ValidationFailed, field_error
from app.db.session import get_db

DbSession = Annotated[Session, Depends(get_db)]
Limit = Annotated[int, Query(ge=1, le=200, description="Page size")]
Offset = Annotated[int, Query(ge=0, description="Items to skip")]


def get_review_provider():
    """The configured model provider, or None (limited mode). Tests override this dependency with a fake."""
    from app.services.review.providers import build_provider

    return build_provider()


# --------------------------------------------------------------------- demo identity (Phase 4)
# BrandPR has no sign-in. The workflow therefore uses an explicit DEMO identity: the caller states who it is and in which role
# (headers X-Actor-Name and X-Actor-Role). The backend enforces what each role may do, but the claim itself is NOT authenticated:
# anyone who can reach the API can assert any role. This is a competition-prototype stand-in, not production authentication.
ACTOR_ROLES = ("creator", "reviewer")


@dataclass(frozen=True)
class Actor:
    name: str
    role: str

    @property
    def is_reviewer(self) -> bool:
        return self.role == "reviewer"


def get_actor(
    x_actor_name: Annotated[str | None, Header(description="Demo identity: who is acting (not authenticated).")] = None,
    x_actor_role: Annotated[str | None, Header(description="Demo role: creator or reviewer (not authenticated).")] = None,
) -> Actor:
    name = (x_actor_name or "").strip()
    role = (x_actor_role or "").strip().lower()
    if not name or not role:
        raise ActorRequired("This action needs an actor. Send the X-Actor-Name and X-Actor-Role headers (demo identity).")
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
    x_actor_name: Annotated[str | None, Header()] = None, x_actor_role: Annotated[str | None, Header()] = None,
) -> Actor | None:
    """For read endpoints: without identity headers the caller is anonymous and is offered no actions."""
    return get_actor(x_actor_name, x_actor_role) if (x_actor_name or x_actor_role) else None


OptionalActor = Annotated[Actor | None, Depends(get_optional_actor)]
