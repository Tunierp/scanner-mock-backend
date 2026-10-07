"""Exceptions métier centralisées + handlers d'erreurs FastAPI (format uniforme)."""
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.constants import MESSAGES, ReasonCode

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Erreur métier : porte un code, un message et un statut HTTP."""

    http_status: int = 500
    code: ReasonCode = ReasonCode.INTERNAL_ERROR

    def __init__(self, message: str | None = None, *, details: dict[str, Any] | None = None):
        self.message = message or MESSAGES[self.code]
        self.details = details
        super().__init__(self.message)


class CardNotFoundError(AppError):
    http_status = 404
    code = ReasonCode.CARD_NOT_FOUND


class InvalidLineError(AppError):
    http_status = 400
    code = ReasonCode.INVALID_LINE


class FareNotFoundError(AppError):
    http_status = 404
    code = ReasonCode.FARE_NOT_FOUND


class DuplicateTransactionError(AppError):
    http_status = 409
    code = ReasonCode.DUPLICATE_TRANSACTION


class TransactionAlreadyProcessedError(AppError):
    http_status = 409
    code = ReasonCode.TRANSACTION_ALREADY_PROCESSED


class ActiveCardAlreadyExistsError(AppError):
    http_status = 409
    code = ReasonCode.ACTIVE_CARD_ALREADY_EXISTS


class CategoryNotFoundError(AppError):
    http_status = 404
    code = ReasonCode.CATEGORY_NOT_FOUND


class PeriodNotFoundError(AppError):
    http_status = 404
    code = ReasonCode.PERIOD_NOT_FOUND


class CorridorNotFoundError(AppError):
    http_status = 404
    code = ReasonCode.CORRIDOR_NOT_FOUND


class SubscriptionFareNotFoundError(AppError):
    http_status = 404
    code = ReasonCode.SUBSCRIPTION_FARE_NOT_FOUND


class ResetForbiddenError(AppError):  # API temporaire de réinitialisation
    http_status = 403
    code = ReasonCode.RESET_FORBIDDEN


class InternalError(AppError):
    http_status = 500
    code = ReasonCode.INTERNAL_ERROR


def error_body(code: str, message: str, details: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": str(code), "message": message}
    if details is not None:
        error["details"] = details
    return {"success": False, "error": error}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": [str(part) for part in err.get("loc", [])], "msg": err.get("msg"), "type": err.get("type")}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content=error_body(ReasonCode.VALIDATION_ERROR, MESSAGES[ReasonCode.VALIDATION_ERROR], details),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = ReasonCode.NOT_FOUND if exc.status_code == 404 else ReasonCode.HTTP_ERROR
        message = MESSAGES[code] if exc.status_code == 404 else str(exc.detail)
        return JSONResponse(status_code=exc.status_code, content=error_body(code, message))

    @app.exception_handler(Exception)
    async def unhandled_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Erreur non gérée", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_body(ReasonCode.INTERNAL_ERROR, MESSAGES[ReasonCode.INTERNAL_ERROR]),
        )
