"""Uniform error responses: {"error": {"code", "message", "requestId"}}. Never leaks internals."""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from google.api_core.exceptions import GoogleAPICallError, RetryError
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from trustbank.observability import REQUEST_ID_HEADER, current_request_id

log = logging.getLogger("trustbank.errors")

_STATUS_CODES = {
    400: "VALIDATION_ERROR",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "INVALID_TRANSITION",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "UNAVAILABLE",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def unauthenticated(message: str = "Authentication required.") -> ApiError:
    return ApiError(401, "UNAUTHENTICATED", message)


def forbidden(message: str = "You do not have access to this resource.") -> ApiError:
    return ApiError(403, "FORBIDDEN", message)


def not_found(message: str = "Not found.") -> ApiError:
    return ApiError(404, "NOT_FOUND", message)


def invalid_transition(message: str) -> ApiError:
    return ApiError(409, "INVALID_TRANSITION", message)


def hold_active(message: str) -> ApiError:
    return ApiError(409, "HOLD_ACTIVE", message)


def validation_error(message: str) -> ApiError:
    return ApiError(422, "VALIDATION_ERROR", message)


def unavailable(message: str = "Service temporarily unavailable.") -> ApiError:
    return ApiError(503, "UNAVAILABLE", message)


class ErrorBody(BaseModel):
    code: str
    message: str
    requestId: str  # noqa: N815 - wire name


class ErrorResponse(BaseModel):
    error: ErrorBody


def error_response(status: int, code: str, message: str) -> JSONResponse:
    request_id = current_request_id()
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "requestId": request_id}},
        headers={REQUEST_ID_HEADER: request_id},
    )


def _validation_message(exc: RequestValidationError) -> str:
    # Field names only: pydantic's `input` can echo secrets such as a PIN.
    fields: list[str] = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path"))
        if loc and loc not in fields:
            fields.append(loc)
    return "Invalid request: " + (", ".join(fields) if fields else "malformed input") + "."


def install_error_handlers(app: FastAPI) -> None:
    async def on_api_error(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, ApiError)
        return error_response(exc.status, exc.code, exc.message)

    async def on_validation(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return error_response(422, "VALIDATION_ERROR", _validation_message(exc))

    async def on_http(_: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        code = _STATUS_CODES.get(exc.status_code, "ERROR")
        message = {404: "Not found.", 405: "Method not allowed."}.get(
            exc.status_code, "Request failed."
        )
        return error_response(exc.status_code, code, message)

    async def on_backend_unavailable(_: Request, exc: Exception) -> JSONResponse:
        log.error("datastore_unavailable", extra={"error_type": type(exc).__name__})
        return error_response(503, "UNAVAILABLE", "Service temporarily unavailable.")

    async def on_unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", extra={"error_type": type(exc).__name__})
        return error_response(500, "INTERNAL_ERROR", "Something went wrong.")

    handlers: dict[Any, Any] = {
        ApiError: on_api_error,
        RequestValidationError: on_validation,
        StarletteHTTPException: on_http,
        GoogleAPICallError: on_backend_unavailable,
        RetryError: on_backend_unavailable,
        Exception: on_unexpected,
    }
    for exc_type, handler in handlers.items():
        app.add_exception_handler(exc_type, handler)
