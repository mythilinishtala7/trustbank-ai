"""Uniform error format and request-scoped logging (no sensitive data)."""

import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
log = logging.getLogger("trustbank")

_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    503: "SERVICE_UNAVAILABLE",
}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message


def _body(status: int, code: str, message: str) -> JSONResponse:
    payload = {"error": {"code": code, "message": message, "requestId": request_id_var.get()}}
    return JSONResponse(payload, status_code=status, headers={"X-Request-ID": request_id_var.get()})


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "msg": record.getMessage(),
            "requestId": request_id_var.get(),
        }
        entry.update(getattr(record, "fields", {}))
        return json.dumps(entry)


def configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(_JsonFormatter())
    log.handlers = [handler]
    log.setLevel(logging.INFO)
    log.propagate = False


def install(app: FastAPI) -> None:
    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        rid = request.headers.get("X-Request-ID", "")
        request_id_var.set(rid if 0 < len(rid) <= 64 else uuid.uuid4().hex[:16])
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id_var.get()
        # Method and path only: never query strings, headers, or bodies.
        log.info(
            "request",
            extra={
                "fields": {
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "ms": round((time.perf_counter() - started) * 1000),
                }
            },
        )
        return response

    @app.exception_handler(ApiError)
    async def api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _body(exc.status, exc.code, exc.message)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _CODES.get(exc.status_code, "ERROR")
        return _body(exc.status_code, code, str(exc.detail) if exc.status_code < 500 else "Error")

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = ", ".join(sorted({".".join(str(p) for p in e["loc"][1:]) for e in exc.errors()}))
        return _body(422, "VALIDATION_ERROR", f"Invalid request: {fields or 'body'}")

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error", extra={"fields": {"type": type(exc).__name__}})
        return _body(503, "SERVICE_UNAVAILABLE", "The service could not complete the request.")
