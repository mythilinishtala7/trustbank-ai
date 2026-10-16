"""HTTP routes for slice 2: health, personas, auth, /me, recipient lookup."""

import re
from typing import Annotated

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from trustbank.api.errors import ApiError, log
from trustbank.api.schemas import (
    ComponentStatus,
    CustomerAuthIn,
    HealthOut,
    InvestigatorAuthIn,
    InvestigatorSessionOut,
    MeOut,
    PersonaOut,
    RecipientLookupOut,
    RecipientOut,
    TokenOut,
    TransactionOut,
)
from trustbank.api.security import (
    Customer,
    Investigator,
    RateLimiter,
    codes_match,
    issue_token,
)
from trustbank.config import Settings
from trustbank.store import DatasetRepository

router = APIRouter(prefix="/api/v1")

_UPI = re.compile(r"^[a-z0-9._-]{2,64}@[a-z]{2,32}$")
_ACCOUNT_NUMBER = re.compile(r"^\d{9,18}$")


def _repo(request: Request) -> DatasetRepository:
    repo: DatasetRepository = request.app.state.repo
    return repo


def _settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


@router.get("/health", response_model=HealthOut)
async def health(request: Request) -> HealthOut:
    def check_firestore() -> bool:
        try:
            _repo(request).ping()
            return True
        except Exception:
            return False

    def check_neo4j() -> bool:
        try:
            request.app.state.neo4j_driver.verify_connectivity()
            return True
        except Exception:
            return False

    fs_ok = await run_in_threadpool(check_firestore)
    neo_ok = await run_in_threadpool(check_neo4j)
    if not (fs_ok and neo_ok):
        log.warning("health degraded", extra={"fields": {"firestore": fs_ok, "neo4j": neo_ok}})
    return HealthOut(
        status="ok" if fs_ok and neo_ok else "degraded",
        firestore=ComponentStatus(status="ok" if fs_ok else "unavailable"),
        neo4j=ComponentStatus(status="ok" if neo_ok else "unavailable"),
        model=ComponentStatus(status="not_configured"),
    )


@router.get("/personas", response_model=list[PersonaOut])
async def personas(request: Request) -> list[PersonaOut]:
    people = await run_in_threadpool(_repo(request).list_demo_personas)
    return [PersonaOut(id=p.id, display_name=p.display_name) for p in people]


@router.post("/auth/customer", response_model=TokenOut)
async def auth_customer(body: CustomerAuthIn, request: Request) -> TokenOut:
    repo = _repo(request)
    customer = await run_in_threadpool(repo.get_customer, body.persona_id)
    if customer is None or not customer.is_demo_persona:
        raise ApiError(404, "NOT_FOUND", "Persona not found.")
    token, expires = issue_token(_settings(request), "customer", customer.id)
    return TokenOut(access_token=token, expires_at=expires, role="customer")


@router.post("/auth/investigator", response_model=TokenOut)
async def auth_investigator(body: InvestigatorAuthIn, request: Request) -> TokenOut:
    settings = _settings(request)
    limiter: RateLimiter = request.app.state.limiter
    client = request.client.host if request.client else "unknown"
    if limiter.blocked(client):
        raise ApiError(429, "RATE_LIMITED", "Too many attempts. Try again shortly.")
    assert settings.investigator_code is not None
    if not codes_match(body.code, settings.investigator_code.get_secret_value()):
        limiter.record_failure(client)
        raise ApiError(401, "UNAUTHORIZED", "Invalid access code.")
    token, expires = issue_token(settings, "investigator", "investigator")
    return TokenOut(access_token=token, expires_at=expires, role="investigator")


@router.get("/investigation/session", response_model=InvestigatorSessionOut)
async def investigation_session(_: Investigator) -> InvestigatorSessionOut:
    return InvestigatorSessionOut(role="investigator")


@router.get("/me", response_model=MeOut)
async def me(principal: Customer, request: Request) -> MeOut:
    repo = _repo(request)

    def load() -> MeOut | None:
        customer = repo.get_customer(principal.subject)
        if customer is None:
            return None
        account = repo.account_for_owner(customer.id)
        history = repo.transactions_from_account(account.id, limit=5) if account else []
        names: dict[str, str] = {}
        for t in history:
            if t.beneficiary_id not in names:
                ben = repo.get_beneficiary(t.beneficiary_id)
                names[t.beneficiary_id] = ben.display_name if ben else "Unknown recipient"
        return MeOut(
            id=customer.id,
            display_name=customer.display_name,
            balance=customer.balance,
            recent_transactions=[
                TransactionOut(
                    id=t.id,
                    recipient_name=names[t.beneficiary_id],
                    amount=t.amount,
                    currency=t.currency,
                    note=t.note,
                    timestamp=t.timestamp,
                )
                for t in history
            ],
        )

    result = await run_in_threadpool(load)
    if result is None:
        raise ApiError(404, "NOT_FOUND", "Customer not found.")
    return result


@router.get("/recipients/lookup", response_model=RecipientLookupOut)
async def lookup_recipient(
    _: Customer, request: Request, q: Annotated[str, Query(min_length=1, max_length=64)]
) -> RecipientLookupOut:
    query = q.strip().lower()
    repo = _repo(request)
    if _UPI.match(query):
        found = await run_in_threadpool(repo.find_beneficiary_by_handle, query)
    elif _ACCOUNT_NUMBER.match(query):
        found = await run_in_threadpool(repo.find_beneficiary_by_account_number, query)
    else:
        raise ApiError(422, "VALIDATION_ERROR", "Enter a UPI id or a 9 to 18 digit account number.")
    if found is None:
        return RecipientLookupOut(found=False)
    return RecipientLookupOut(
        found=True,
        recipient=RecipientOut(id=found.id, display_name=found.display_name, handle=found.handle),
    )
