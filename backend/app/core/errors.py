"""Global API exception handling with consistent JSON responses."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette import status

from app.core.logging import get_logger

logger = get_logger(__name__)


def _error_body(
    *,
    code: str,
    message: str,
    detail: Any,
    request: Request,
) -> dict[str, Any]:
    request_id = getattr(request.state, "request_id", "n/a")
    return {
        "error": {
            "code": code,
            "message": message,
            "details": detail,
        },
        "detail": message,
        "path": request.url.path,
        "request_id": request_id,
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        message = detail if isinstance(detail, str) else "Request failed."
        logger.warning("HTTPException %s on %s: %s", exc.status_code, request.url.path, message)
        return JSONResponse(
            status_code=exc.status_code,
            content=_error_body(
                code="http_error",
                message=message,
                detail=detail,
                request=request,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = exc.errors()
        logger.warning("Validation error on %s: %s", request.url.path, details)
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=_error_body(
                code="validation_error",
                message="Request validation failed.",
                detail=details,
                request=request,
            ),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s", request.url.path)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=_error_body(
                code="internal_error",
                message="Internal server error.",
                detail=str(exc),
                request=request,
            ),
        )

