"""Access to application services from request handlers."""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from fastapi import Request

from trustbank.auth import AttemptLimiter, TokenService
from trustbank.config import Settings
from trustbank.errors import not_found
from trustbank.graph import GraphService
from trustbank.payments.investigation import InvestigationService
from trustbank.payments.service import PaymentService
from trustbank.store import DatasetRepository

_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


@dataclass
class Services:
    settings: Settings
    dataset: DatasetRepository
    graph: GraphService
    payments: PaymentService
    investigation: InvestigationService
    tokens: TokenService
    limiter: AttemptLimiter
    clock: Callable[[], datetime]
    payment_repo_ping: Callable[[], bool]


def services(request: Request) -> Services:
    svc: Services = request.app.state.services
    return svc


def valid_id(value: str) -> str:
    if not _ID.match(value):
        raise not_found()
    return value
