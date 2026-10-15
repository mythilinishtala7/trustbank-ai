"""Signed tokens, role dependencies and the investigator-code rate limiter."""

import hmac
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

import jwt
from fastapi import Depends, Request

from trustbank.api.errors import ApiError
from trustbank.config import Settings

Role = Literal["customer", "investigator"]
_ALGORITHM = "HS256"


@dataclass(frozen=True)
class Principal:
    role: Role
    subject: str


def issue_token(settings: Settings, role: Role, subject: str) -> tuple[str, datetime]:
    ttl = (
        timedelta(hours=settings.customer_token_hours)
        if role == "customer"
        else timedelta(minutes=settings.investigator_token_minutes)
    )
    expires = datetime.now(UTC) + ttl
    assert settings.token_secret is not None
    token = jwt.encode(
        {"sub": subject, "role": role, "exp": expires, "iat": datetime.now(UTC)},
        settings.token_secret.get_secret_value(),
        algorithm=_ALGORITHM,
    )
    return token, expires


def _principal(request: Request) -> Principal:
    settings: Settings = request.app.state.settings
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "UNAUTHORIZED", "Authentication required.")
    assert settings.token_secret is not None
    try:
        claims = jwt.decode(
            token,
            settings.token_secret.get_secret_value(),
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "sub", "role"]},
        )
    except jwt.PyJWTError:
        raise ApiError(401, "UNAUTHORIZED", "Session is missing or has expired.") from None
    if claims["role"] not in ("customer", "investigator"):
        raise ApiError(401, "UNAUTHORIZED", "Session is missing or has expired.")
    return Principal(role=claims["role"], subject=str(claims["sub"]))


def require_customer(request: Request) -> Principal:
    principal = _principal(request)
    if principal.role != "customer":
        raise ApiError(403, "FORBIDDEN", "This action is not available for your session.")
    return principal


def require_investigator(request: Request) -> Principal:
    principal = _principal(request)
    if principal.role != "investigator":
        raise ApiError(403, "FORBIDDEN", "This action is not available for your session.")
    return principal


Customer = Annotated[Principal, Depends(require_customer)]
Investigator = Annotated[Principal, Depends(require_investigator)]


def codes_match(supplied: str, expected: str) -> bool:
    return hmac.compare_digest(supplied.encode(), expected.encode())


class RateLimiter:
    """Counts failed attempts per client address in a sliding window (single instance)."""

    def __init__(self, attempts: int, window_seconds: int = 60) -> None:
        self._attempts, self._window = attempts, window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _recent(self, key: str) -> deque[float]:
        hits = self._hits[key]
        now = time.monotonic()
        while hits and now - hits[0] > self._window:
            hits.popleft()
        return hits

    def blocked(self, key: str) -> bool:
        return len(self._recent(key)) >= self._attempts

    def record_failure(self, key: str) -> None:
        self._recent(key).append(time.monotonic())
