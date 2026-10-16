"""Frozen contracts shared by agents, policy, payments and the API (task 0.1).

API JSON is camelCase (see `ApiModel`). Python code uses snake_case.
Agents return evidence and recommendations only; they never change payment state.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from trustbank.domain import Provenance


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Level(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class Action(StrEnum):
    PROCEED = "PROCEED"
    REVIEW = "REVIEW"
    HOLD = "HOLD"


class PaymentStatus(StrEnum):
    INITIATED = "INITIATED"
    ASSESSING = "ASSESSING"
    QUESTIONNAIRE = "QUESTIONNAIRE"
    REVIEW = "REVIEW"
    HOLD_ACTIVE = "HOLD_ACTIVE"
    HOLD_EXPIRED = "HOLD_EXPIRED"
    READY_FOR_AUTH = "READY_FOR_AUTH"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


TERMINAL_STATUSES = frozenset({PaymentStatus.COMPLETED, PaymentStatus.CANCELLED})

AgentId = Literal["anomaly", "fraud_network", "questionnaire"]
AgentStatus = Literal["OK", "FAILED", "TIMEOUT", "DEGRADED"]
FreeTextClass = Literal["none", "coercion_indicated", "scam_script_indicated", "unclear"]


class Evidence(ApiModel):
    id: str  # stable code, e.g. "network.fan_in"
    summary: str
    provenance: Provenance
    source_entity_ids: list[str] = Field(default_factory=list)
    points: int = 0  # 0 = context only (for example the cleared-by-long-dwell evidence)


class AgentFinding(ApiModel):
    agent_id: AgentId
    status: AgentStatus
    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    evidence: list[Evidence] = Field(default_factory=list)
    error: str | None = None


class Option(ApiModel):
    value: str
    label: str


class Question(ApiModel):
    id: str  # one of QUESTION_TYPES
    text: str
    signal_ids: list[str] = Field(default_factory=list)
    options: list[Option]
    allow_free_text: bool = False


class Answer(ApiModel):
    question_id: str
    option: str
    free_text: str | None = Field(default=None, max_length=300)


QUESTION_TYPES = (
    "source_of_details",
    "promised_benefit",
    "urgency_or_secrecy",
    "recipient_relationship",
)


class PolicyConfig(ApiModel):
    anomaly_weight: float = 0.4
    network_weight: float = 0.6
    elevated_threshold: int = 30
    high_threshold: int = 60
    hold_seconds: int = 180
    context_cap: int = 10  # free-text classification cap
    evidence_cap_score: int = (
        59  # applies without network evidence unless context >= evidence_cap_context
    )
    evidence_cap_context: int = 40


class Aggregate(ApiModel):
    anomaly_score: int
    network_score: int
    pre_score: int
    context_points: int
    final_score: int
    level: Level
    action: Action
    elevated: bool
    incomplete: bool
    evidence_cap_applied: bool


class ToolCall(ApiModel):
    agent_id: str
    tool: str
    parameters: dict[str, Any]
    result_summary: str
    started_at: datetime
    duration_ms: int


class Explanation(ApiModel):
    text: str
    reasons: list[str]
    evidence_ids: list[str]
    status: Literal["OK", "DEGRADED"]


TimelineAgent = Literal[
    "orchestrator", "anomaly", "fraud_network", "questionnaire", "explainer", "policy"
]
TimelineType = Literal[
    "STARTED", "TOOL_CALL", "FINDING", "FALLBACK", "COMPLETED", "FAILED", "STATE_CHANGE"
]


class TraceEvent(ApiModel):
    seq: int  # per payment, starts at 1, strictly increasing
    at: datetime
    agent_id: TimelineAgent
    type: TimelineType
    status: str | None = None
    duration_ms: int | None = None
    tool: str | None = None
    parameters: dict[str, Any] | None = None
    result_summary: str | None = None
    message: str


class TraceSink(Protocol):
    """Receives timeline events as they happen. Implemented by the payment service."""

    def emit(
        self,
        agent_id: TimelineAgent,
        type: TimelineType,
        message: str,
        *,
        status: str | None = None,
        duration_ms: int | None = None,
        tool: str | None = None,
        parameters: dict[str, Any] | None = None,
        result_summary: str | None = None,
    ) -> None: ...


class PaymentContext(BaseModel):
    """The only inputs agents receive: ids, amount, time. No scenario labels (scenario blindness)."""

    model_config = ConfigDict(frozen=True)

    payment_id: str
    customer_id: str
    beneficiary_id: str
    amount: int
    now: datetime


class DetectorResult(BaseModel):
    anomaly: AgentFinding
    fraud_network: AgentFinding
    tool_calls: list[ToolCall] = Field(default_factory=list)


class QuestionnaireResult(BaseModel):
    questions: list[Question]
    degraded: bool = False


class AnswerResult(BaseModel):
    finding: (
        AgentFinding  # agent_id="questionnaire", USER_PROVIDED evidence, score = context points
    )


class Orchestrator(Protocol):
    """ADK-backed implementation lives in `trustbank.agents`. Tests may substitute a stub model."""

    model_name: str

    async def run_detectors(self, ctx: PaymentContext, trace: TraceSink) -> DetectorResult: ...

    async def ask_questions(
        self, ctx: PaymentContext, findings: list[AgentFinding], trace: TraceSink
    ) -> QuestionnaireResult: ...

    async def interpret_answers(
        self,
        ctx: PaymentContext,
        questions: list[Question],
        answers: list[Answer],
        findings: list[AgentFinding],
        config: PolicyConfig,
        trace: TraceSink,
    ) -> AnswerResult: ...

    async def explain(
        self,
        ctx: PaymentContext,
        findings: list[AgentFinding],
        aggregate: Aggregate,
        trace: TraceSink,
    ) -> Explanation: ...
