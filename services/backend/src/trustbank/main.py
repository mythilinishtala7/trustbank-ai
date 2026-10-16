"""FastAPI application factory. `uvicorn trustbank.main:app` builds the real app lazily."""

import logging
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trustbank.api import customer, investigation, public
from trustbank.api.deps import Services
from trustbank.auth import AttemptLimiter, TokenService
from trustbank.config import Settings, get_settings
from trustbank.contracts import Orchestrator
from trustbank.errors import ErrorResponse, install_error_handlers
from trustbank.graph import GraphService
from trustbank.observability import REQUEST_ID_HEADER, RequestIdMiddleware, configure_logging
from trustbank.payments.investigation import InvestigationService
from trustbank.payments.repo import PaymentRepository
from trustbank.payments.service import PaymentService
from trustbank.payments.trace import TraceHub
from trustbank.policy import policy_config_from
from trustbank.store import DatasetRepository, create_client

API_PREFIX = "/api/v1"
log = logging.getLogger("trustbank.app")

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    code: {"model": ErrorResponse, "description": text}
    for code, text in {
        401: "Missing, invalid or expired token",
        403: "Role not allowed",
        404: "Not found",
        409: "Invalid transition or hold active",
        422: "Validation error",
        429: "Too many attempts",
        503: "Dependency unavailable",
    }.items()
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def create_app(
    settings: Settings | None = None,
    *,
    orchestrator: Orchestrator | None = None,
    graph: GraphService | None = None,
    repo: DatasetRepository | None = None,
    clock: Callable[[], datetime] | None = None,
    sse_ping_interval: float = 15.0,
    sse_poll_interval: float = 1.0,
) -> FastAPI:
    settings = settings or get_settings()
    settings.validate_for_serving()
    configure_logging()
    clock = clock or _utc_now

    repo = repo or DatasetRepository(create_client(settings))
    if graph is None:
        from trustbank.graph import build_graph_service

        graph = build_graph_service(settings)
    if orchestrator is None:
        from trustbank.agents import build_orchestrator

        orchestrator = build_orchestrator(settings, graph, repo)

    payment_repo = PaymentRepository(repo.client)
    hub = TraceHub(payment_repo, clock)
    payments = PaymentService(
        orchestrator=orchestrator,
        graph=graph,
        dataset=repo,
        payments=payment_repo,
        hub=hub,
        config=policy_config_from(settings),
        clock=clock,
    )
    investigation_service = InvestigationService(
        payments=payments,
        dataset=repo,
        repo=payment_repo,
        graph=graph,
        hub=hub,
        clock=clock,
        ping_interval=sse_ping_interval,
        poll_interval=sse_poll_interval,
    )
    assert settings.token_secret is not None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        yield
        close = getattr(graph, "close", None)
        if callable(close):
            close()

    app = FastAPI(
        title="TrustBank AI",
        description="Agentic fraud prevention before payment authorization (synthetic, simulated).",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.tokens = TokenService(
        settings.token_secret.get_secret_value(), timedelta(hours=settings.token_ttl_hours), clock
    )
    import time

    app.state.services = Services(
        settings=settings,
        dataset=repo,
        graph=graph,
        payments=payments,
        investigation=investigation_service,
        tokens=app.state.tokens,
        limiter=AttemptLimiter(
            settings.investigator_rate_limit,
            settings.investigator_rate_window_seconds,
            time.monotonic,
        ),
        clock=clock,
        payment_repo_ping=payment_repo.ping,
    )

    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIdMiddleware)

    for router in (public.router, customer.router, investigation.router):
        app.include_router(router, prefix=API_PREFIX, responses=_ERROR_RESPONSES)
    app.add_api_route("/health", public.health, methods=["GET"], include_in_schema=False)
    return app


def __getattr__(name: str) -> FastAPI:
    # Lazy so importing this module (tests, tooling) never needs secrets or live dependencies.
    if name == "app":
        app = create_app()
        globals()["app"] = app
        return app
    raise AttributeError(name)
