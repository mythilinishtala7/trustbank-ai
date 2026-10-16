"""Persisted payment and assessment records (server-side; never returned to customers as is)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from trustbank.contracts import (
    AgentFinding,
    Aggregate,
    Answer,
    ApiModel,
    Explanation,
    PaymentStatus,
    PolicyConfig,
    Question,
    ToolCall,
)


class PaymentDoc(BaseModel):
    """Firestore `payments/{id}`. Holds server-side data (aggregate, scores) for investigators."""

    model_config = ConfigDict(extra="forbid")

    id: str
    customer_id: str
    customer_name: str
    beneficiary_id: str
    recipient_name: str | None
    recipient_handle: str
    recipient_verified: bool
    amount: int
    note: str = ""
    status: PaymentStatus
    created_at: datetime
    updated_at: datetime
    hold_until: datetime | None = None
    verified: bool = False
    questions: list[Question] = Field(default_factory=list)
    explanation: Explanation | None = None
    aggregate: Aggregate | None = None
    transaction_id: str | None = None


class Assessment(ApiModel):
    """Immutable decision record (`assessments/{id}`), exposed only through /investigation."""

    id: str
    stage: Literal["INITIAL", "FINAL"]
    created_at: datetime
    complete: bool
    findings: list[AgentFinding]
    aggregate: Aggregate
    config: PolicyConfig
    questions: list[Question] = Field(default_factory=list)
    answers: list[Answer] = Field(default_factory=list)
    explanation: Explanation | None = None
    model: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    started_at: datetime
    ended_at: datetime
    duration_ms: int
