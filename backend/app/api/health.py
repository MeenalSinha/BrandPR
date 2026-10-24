from fastapi import APIRouter, Response
from sqlalchemy import text

from app import __version__
from app.api.deps import DbSession
from app.core.config import get_settings
from app.core.errors import AppError
from app.schemas.common import DatabaseHealthResponse, ErrorResponse, HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse, summary="Liveness check")
def health() -> HealthResponse:
    return HealthResponse(status="ok", service="brandpr-api", version=__version__, environment=get_settings().app_env)


@router.get(
    "/db", response_model=DatabaseHealthResponse, responses={503: {"model": ErrorResponse}},
    summary="Database connectivity check",
)
def health_db(db: DbSession) -> DatabaseHealthResponse:
    db.execute(text("SELECT 1"))
    version = db.scalar(text("SHOW server_version"))
    return DatabaseHealthResponse(status="ok", database="connected", server_version=version)
