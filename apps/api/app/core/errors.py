"""Errores de dominio con códigos estables y handlers globales.

Formato único de error hacia el cliente:
    { "error": { "code", "message", "details", "traceId" } }
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import current_trace_id

log = structlog.get_logger()


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    http_status = 400

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        http_status: int | None = None,
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if http_status:
            self.http_status = http_status
        self.details = details or []


class UnauthorizedError(DomainError):
    code = "UNAUTHORIZED"
    http_status = 401


class ForbiddenError(DomainError):
    code = "FORBIDDEN"
    http_status = 403


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    http_status = 404


class ConflictError(DomainError):
    code = "CONFLICT"
    http_status = 409


class WindowExpiredError(ConflictError):
    """Fuera de la ventana de 24h de WhatsApp solo se permiten plantillas."""

    code = "WINDOW_EXPIRED"


class AccountPausedError(ConflictError):
    code = "ACCOUNT_PAUSED"


class StageAmbiguousError(ConflictError):
    code = "STAGE_AMBIGUOUS"


class RetryableTaskError(Exception):
    """Señala a la cola que el intento falló por una causa transitoria
    (5xx, red, rate limit) y debe reintentarse con backoff."""


def _error_body(code: str, message: str, details: list[Any] | None = None) -> dict:
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details or [],
            "traceId": current_trace_id(),
        }
    }


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(_request: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=_error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in err.get("loc", [])), "issue": err.get("msg")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=_error_body("VALIDATION_ERROR", "Payload inválido", details),
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_exception", path=request.url.path, exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_error_body("INTERNAL", "Error interno del servidor"),
        )
