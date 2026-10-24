import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import brands, campaigns, content, documents, facts, guidelines, health, impacts, insights, reviews, workflow
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging

logger = logging.getLogger("brandpr")


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    settings.assert_safe_for_environment()

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        settings.storage_dir.mkdir(parents=True, exist_ok=True)
        try:
            from app.db.session import get_db
            from app.services.review.pipeline import fail_interrupted_runs

            db = next(get_db())
            try:
                n = fail_interrupted_runs(db)
                if n:
                    logger.warning("Marked %d interrupted review run(s) as failed", n)
            finally:
                db.close()
        except Exception:  # the API must still start if the database is briefly unavailable
            logger.warning("Could not check for interrupted review runs at startup", exc_info=True)
        logger.info("BrandPR API %s starting (env=%s, storage=%s)", __version__, settings.app_env, "configured")
        yield

    app = FastAPI(
        title="BrandPR API",
        version=__version__,
        description="Approved brand knowledge (Phase 1), content review with evidence-backed findings, ProofGraph (Phase 2), Claim Ledger fact-change impacts (Phase 3), content revisions, human approval and impact resolution (Phase 4), Guideline Lint, Policy Sandbox & Governance Intelligence (Phase 5), and Campaign Intelligence, Portfolio Audits & Release Readiness (Phase 6).",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.docs_enabled else None,
        redoc_url="/api/redoc" if settings.docs_enabled else None,
        openapi_url="/api/openapi.json" if settings.docs_enabled else None,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept", "X-Actor-Name", "X-Actor-Role"],
        expose_headers=["X-Request-ID", "Content-Disposition"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info(
            "%s %s -> %s (%.0f ms) [%s]", request.method, request.url.path, response.status_code,
            (time.perf_counter() - started) * 1000, request.state.request_id,
        )
        return response

    register_error_handlers(app)
    api = APIRouter(prefix="/api")
    for module in (health, brands, documents, facts, content, reviews, impacts, workflow, guidelines, insights, campaigns):
        api.include_router(module.router)
    app.include_router(api)
    return app



app = create_app()
