"""Request and response models (camelCase on the wire)."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from trustbank.contracts import Answer, ApiModel, TraceEvent
from trustbank.graph.views import GraphView
from trustbank.payments.models import Assessment


class Persona(ApiModel):
    id: str
    display_name: str
    handle: str
    blurb: str


class CustomerLoginRequest(ApiModel):
    persona_id: Annotated[str, StringConstraints(min_length=1, max_length=64)]


class InvestigatorLoginRequest(ApiModel):
    code: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class CustomerSession(ApiModel):
    token: str
    role: Literal["customer"] = "customer"
    expires_at: datetime
    display_name: str


class InvestigatorSession(ApiModel):
    token: str
    role: Literal["investigator"] = "investigator"
    expires_at: datetime


class RecentTransaction(ApiModel):
    id: str
    recipient_name: str
    amount: int
    note: str
    timestamp: datetime


class Me(ApiModel):
    display_name: str
    handle: str
    balance: int
    recent_transactions: list[RecentTransaction]


class RecipientLookup(ApiModel):
    found: bool
    verified: bool
    display_name: str | None
    handle: str
    masked_account: str | None


class CreatePaymentRequest(ApiModel):
    recipient: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    amount: Annotated[int, Field(strict=True, ge=1, le=10_000_000)]
    note: Annotated[str, StringConstraints(max_length=80)] | None = None


class AnswersRequest(ApiModel):
    answers: Annotated[list[Answer], Field(min_length=1, max_length=3)]


class AuthorizeRequest(ApiModel):
    pin: Annotated[str, StringConstraints(pattern=r"^\d{4,6}$")]


class HealthChecks(ApiModel):
    firestore: Literal["ok", "down"]
    neo4j: Literal["ok", "down"] = Field(alias="neo4j")
    model: Literal["ok", "down", "unchecked"]


class Health(ApiModel):
    status: Literal["ok", "degraded"]
    checks: HealthChecks


class TransactionListItem(ApiModel):
    transaction_id: str
    customer_name: str
    recipient_name: str
    amount: int
    status: str
    created_at: datetime


class TransactionSummary(ApiModel):
    customer_id: str
    customer_name: str
    recipient_id: str
    recipient_name: str
    amount: int
    note: str
    timestamp: datetime
    status: str


class InvestigationTransaction(ApiModel):
    transaction_id: str
    kind: Literal["PAYMENT", "HISTORICAL"]
    simulated: bool = True
    summary: TransactionSummary
    assessments: list[Assessment]
    graph: GraphView


class TimelineResponse(ApiModel):
    transaction_id: str
    payment_status: str | None
    done: bool
    events: list[TraceEvent]
