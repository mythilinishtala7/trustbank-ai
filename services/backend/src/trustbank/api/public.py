import asyncio
import hashlib
import hmac

from fastapi import APIRouter, Depends, Request

from trustbank.api.deps import Services, services
from trustbank.api.schemas import (
    CustomerLoginRequest,
    CustomerSession,
    Health,
    HealthChecks,
    InvestigatorLoginRequest,
    InvestigatorSession,
    Persona,
)
from trustbank.errors import ApiError, not_found, unauthenticated

router = APIRouter()
_CHECK_TIMEOUT = 4.0


async def _check(probe: object) -> bool:
    try:
        return bool(await asyncio.wait_for(asyncio.to_thread(probe), timeout=_CHECK_TIMEOUT))  # type: ignore[arg-type]
    except Exception:
        return False


@router.get("/health", response_model=Health, tags=["public"])
async def health(svc: Services = Depends(services)) -> Health:
    firestore_ok, neo4j_ok = await asyncio.gather(
        _check(svc.payment_repo_ping), _check(svc.graph.ping)
    )
    checks = HealthChecks(
        firestore="ok" if firestore_ok else "down",
        neo4j="ok" if neo4j_ok else "down",
        model="unchecked",
    )
    return Health(status="ok" if firestore_ok and neo4j_ok else "degraded", checks=checks)


@router.get("/personas", response_model=list[Persona], tags=["public"])
async def personas(svc: Services = Depends(services)) -> list[Persona]:
    customers = await asyncio.to_thread(svc.dataset.demo_personas)
    return [
        Persona(id=c.id, display_name=c.display_name, handle=c.handle, blurb="Demo customer")
        for c in customers
    ]


@router.post("/auth/customer", response_model=CustomerSession, tags=["auth"])
async def login_customer(
    body: CustomerLoginRequest, svc: Services = Depends(services)
) -> CustomerSession:
    customer = await asyncio.to_thread(svc.dataset.get_customer, body.persona_id)
    if customer is None or not customer.is_demo_persona:
        raise not_found("Persona not found.")
    token, expires = svc.tokens.issue("customer", customer.id)
    return CustomerSession(token=token, expires_at=expires, display_name=customer.display_name)


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode()).digest()


@router.post("/auth/investigator", response_model=InvestigatorSession, tags=["auth"])
async def login_investigator(
    body: InvestigatorLoginRequest, request: Request, svc: Services = Depends(services)
) -> InvestigatorSession:
    client = request.client.host if request.client else "unknown"
    if svc.limiter.blocked(client):
        raise ApiError(429, "RATE_LIMITED", "Too many attempts. Please try again later.")
    assert svc.settings.investigator_code is not None
    expected = svc.settings.investigator_code.get_secret_value()
    if not hmac.compare_digest(_digest(body.code), _digest(expected)):
        svc.limiter.record_failure(client)
        raise unauthenticated("Invalid access code.")
    svc.limiter.reset(client)
    token, expires = svc.tokens.issue("investigator", "investigator")
    return InvestigatorSession(token=token, expires_at=expires)
