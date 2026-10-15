from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from trustbank.api import errors
from trustbank.api.routes import router
from trustbank.api.security import RateLimiter
from trustbank.config import Settings, get_settings
from trustbank.graph import create_driver
from trustbank.store import DatasetRepository, create_client


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    errors.configure_logging()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.repo = DatasetRepository(create_client(settings))
        app.state.neo4j_driver = create_driver(settings)
        yield
        app.state.neo4j_driver.close()

    app = FastAPI(
        title="TrustBank AI",
        description="Agentic fraud prevention before payment authorization (synthetic data).",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.limiter = RateLimiter(settings.investigator_attempts_per_minute)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    errors.install(app)
    app.include_router(router)
    return app
