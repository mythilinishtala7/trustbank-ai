"""Signed session tokens, role dependencies and the investigator-code rate limiter."""

import base64
import hashlib
import hmac
import json
import threading
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from trustbank.errors import forbidden, unauthenticated

Role = Literal["customer", "investigator"]
_PREFIX = "tb1"


@dataclass(frozen=True)
class Principal:
    role: Role
    subject: str


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class TokenService:
    def __init__(self, secret: str, ttl: timedelta, clock: Callable[[], datetime]) -> None:
        self._key = secret.encode()
        self._ttl = ttl
        self._clock = clock

    def _sign(self, body: str) -> str:
        return _b64(hmac.new(self._key, body.encode(), hashlib.sha256).digest())

    def issue(self, role: Role, subject: str) -> tuple[str, datetime]:
        now = self._clock()
        expires = now + self._ttl
        payload = {
            "role": role,
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
        }
        body = _b64(json.dumps(payload, separators=(",", ":")).encode())
        return f"{_PREFIX}.{body}.{self._sign(body)}", expires

    def verify(self, token: str) -> Principal:
        try:
            prefix, body, signature = token.split(".")
            if prefix != _PREFIX or not hmac.compare_digest(signature, self._sign(body)):
                raise ValueError
            payload = json.loads(_unb64(body))
            role, subject, exp = payload["role"], payload["sub"], int(payload["exp"])
            if role not in ("customer", "investigator") or not isinstance(subject, str):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise unauthenticated("Invalid or expired session.") from None
        if self._clock().timestamp() >= exp:
            raise unauthenticated("Invalid or expired session.")
        return Principal(role=role, subject=subject)


class AttemptLimiter:
    """Sliding window over failed attempts per key (client IP)."""

    def __init__(self, limit: int, window_seconds: int, now: Callable[[], float]) -> None:
        self._limit = limit
        self._window = window_seconds
        self._now = now
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _prune(self, key: str) -> deque[float]:
        cutoff = self._now() - self._window
        failures = self._failures[key]
        while failures and failures[0] <= cutoff:
            failures.popleft()
        return failures

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._prune(key)) >= self._limit

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._prune(key).append(self._now())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


_bearer = HTTPBearer(
    auto_error=False, description="Session token from /auth/customer or /auth/investigator"
)


def _principal(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> Principal:
    if credentials is None or credentials.scheme.lower() != "bearer" or not credentials.credentials:
        raise unauthenticated()
    tokens: TokenService = request.app.state.tokens
    return tokens.verify(credentials.credentials.strip())


def require_customer(principal: Principal = Depends(_principal)) -> Principal:
    if principal.role != "customer":
        raise forbidden()
    return principal


def require_investigator(principal: Principal = Depends(_principal)) -> Principal:
    if principal.role != "investigator":
        raise forbidden()
    return principal
