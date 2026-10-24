"""Application errors and the single structured error format returned by the API.

Every error response has the shape:
  {"error": {"code": str, "message": str, "details": [{"field": str|None, "message": str}], "request_id": str|None}}
Internal exceptions never leak stack traces or filesystem paths to clients.
"""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("brandpr.errors")


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, details: list[dict[str, Any]] | None = None, code: str | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []
        if code:
            self.code = code


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ActorRequired(AppError):
    status_code = 401
    code = "actor_required"


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class ServiceUnavailable(AppError):
    status_code = 503
    code = "service_unavailable"


class ValidationFailed(AppError):
    status_code = 422
    code = "validation_error"


class PayloadTooLarge(AppError):
    status_code = 413
    code = "file_too_large"


class UnsupportedMediaType(AppError):
    status_code = 415
    code = "unsupported_file_type"


def field_error(field: str | None, message: str) -> dict[str, Any]:
    return {"field": field, "message": message}


def _body(request: Request, code: str, message: str, details: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "request_id": getattr(request.state, "request_id", None),
        }
    }


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content=_body(request, exc.code, exc.message, exc.details))

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        details = []
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path", "form")]
            details.append(field_error(".".join(loc) or None, str(err.get("msg", "Invalid value"))))
        return JSONResponse(
            status_code=422,
            content=_body(request, "validation_error", "The request data is invalid.", details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return JSONResponse(status_code=exc.status_code, content=_body(request, code, str(exc.detail)))

    @app.exception_handler(IntegrityError)
    async def _integrity(request: Request, exc: IntegrityError):
        logger.warning("Integrity error: %s", exc.orig)
        return JSONResponse(
            status_code=409,
            content=_body(request, "integrity_error", "The change conflicts with existing data and was not saved."),
        )

    @app.exception_handler(OperationalError)
    async def _operational(request: Request, exc: OperationalError):
        logger.error("Database unavailable: %s", exc.orig)
        return JSONResponse(
            status_code=503,
            content=_body(request, "database_unavailable", "The database is currently unavailable."),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_body(request, "internal_error", "An unexpected error occurred."),
        )
