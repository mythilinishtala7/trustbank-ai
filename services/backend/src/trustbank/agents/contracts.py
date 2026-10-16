"""Typed agent contracts and the validators that guard them.

Agents return evidence and recommendations only. Nothing here carries a payment decision.
"""

import re
from collections.abc import Collection
from enum import StrEnum
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from trustbank.domain import Provenance

MAX_QUESTIONS = 3
MAX_FREE_TEXT = 300

AgentId = Literal["anomaly", "fraud_network", "questionnaire"]
FindingStatus = Literal["OK", "FAILED", "TIMEOUT", "DEGRADED"]


class _Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Evidence(_Contract):
    id: str = Field(pattern=r"^[a-z_]+\.[a-z0-9_]+$")  # stable code, e.g. "network.fan_in"
    summary: str = Field(min_length=1, max_length=300)
    provenance: Provenance
    source_entity_ids: tuple[str, ...] = ()
    points: int = Field(ge=0, le=100)


class AgentFinding(_Contract):
    agent_id: AgentId
    status: FindingStatus
    score: int = Field(ge=0, le=100)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[Evidence, ...] = ()
    error: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        ids = [e.id for e in self.evidence]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence ids must be unique within a finding")
        if self.status in ("FAILED", "TIMEOUT"):
            if self.error is None:
                raise ValueError(f"{self.status} finding must carry an error")
            if self.evidence or self.score:
                raise ValueError(f"{self.status} finding must not carry a score or evidence")
        return self

    @classmethod
    def failed(cls, agent_id: AgentId, error: str, *, timeout: bool = False) -> Self:
        return cls(
            agent_id=agent_id,
            status="TIMEOUT" if timeout else "FAILED",
            score=0,
            confidence=0.0,
            error=error,
        )


class QuestionType(StrEnum):
    SOURCE_OF_DETAILS = "source_of_details"
    PROMISED_BENEFIT = "promised_benefit"
    URGENCY_OR_SECRECY = "urgency_or_secrecy"
    RECIPIENT_RELATIONSHIP = "recipient_relationship"


class Option(_Contract):
    code: str = Field(pattern=r"^[a-z_]+$")
    label: str = Field(min_length=1, max_length=120)


# Fixed by the backend. The LLM picks wording and which types to ask, nothing else.
OPTION_SETS: dict[QuestionType, tuple[Option, ...]] = {
    QuestionType.SOURCE_OF_DETAILS: (
        Option(code="known_in_person", label="I know them and got the details from them directly"),
        Option(code="invoice_or_bill", label="From an invoice or bill I was sent"),
        Option(code="message_or_call", label="From a message, call or link someone sent me"),
        Option(code="online_listing", label="From an online listing or advert"),
    ),
    QuestionType.PROMISED_BENEFIT: (
        Option(code="none", label="Nobody has promised me anything"),
        Option(code="goods_or_service", label="Goods or a service I ordered"),
        Option(code="returns_or_reward", label="Returns, a reward or a prize"),
        Option(code="refund_or_recovery", label="A refund or recovery of money"),
    ),
    QuestionType.URGENCY_OR_SECRECY: (
        Option(code="no_pressure", label="No, I am deciding on my own time"),
        Option(code="asked_to_hurry", label="I was asked to pay quickly"),
        Option(code="asked_to_keep_secret", label="I was asked not to tell anyone"),
        Option(code="both", label="Both"),
    ),
    QuestionType.RECIPIENT_RELATIONSHIP: (
        Option(code="family_or_friend", label="Family or a friend"),
        Option(code="regular_business", label="A business I have paid before"),
        Option(code="new_business", label="A business I am paying for the first time"),
        Option(code="stranger", label="Someone I have not met"),
    ),
}


class Question(_Contract):
    id: QuestionType
    text: str = Field(min_length=1, max_length=240)
    signal_ids: tuple[str, ...] = Field(min_length=1)
    options: tuple[Option, ...]


class FreeTextClass(StrEnum):
    NONE = "none"
    COERCION_INDICATED = "coercion_indicated"
    SCAM_SCRIPT_INDICATED = "scam_script_indicated"
    UNCLEAR = "unclear"


class FreeTextVerdict(_Contract):
    label: FreeTextClass
    confidence: float = Field(ge=0.0, le=1.0)


class Answer(_Contract):
    question_id: QuestionType
    option: str
    free_text: str | None = Field(default=None, max_length=MAX_FREE_TEXT)

    @model_validator(mode="after")
    def _option_allowed(self) -> Self:
        if self.option not in {o.code for o in OPTION_SETS[self.question_id]}:
            raise ValueError("option is not allowed for this question")
        return self


class Explanation(_Contract):
    text: str = Field(min_length=1, max_length=600)
    cited_evidence_ids: tuple[str, ...] = Field(min_length=1)


class ContractViolation(ValueError):
    """Agent output failed validation. The caller records FAILED or DEGRADED and discards it."""


def validate_grounding(finding: AgentFinding, tool_entity_ids: Collection[str]) -> None:
    """Every entity an agent cites must be one its tools actually returned."""
    known = set(tool_entity_ids)
    for ev in finding.evidence:
        stray = [i for i in ev.source_entity_ids if i not in known]
        if stray:
            raise ContractViolation(f"{ev.id} cites entities no tool returned: {stray}")


def validate_questions(
    questions: Collection[Question], present_signal_ids: Collection[str]
) -> None:
    """At most 3 distinct questions, tied to present signals, with the backend's fixed options."""
    if len(questions) > MAX_QUESTIONS:
        raise ContractViolation(f"more than {MAX_QUESTIONS} questions")
    if len({q.id for q in questions}) != len(questions):
        raise ContractViolation("duplicate question type")
    present = set(present_signal_ids)
    for q in questions:
        if not set(q.signal_ids) <= present:
            raise ContractViolation(f"question {q.id} cites signals that are not present")
        if q.options != OPTION_SETS[q.id]:
            raise ContractViolation(f"question {q.id} options differ from the fixed set")


_GUILT = re.compile(
    r"\b(is|are|was|were)\s+(a\s+)?(fraud\w*|scam\w*|criminal\w*|mule\w*|guilty)\b|"
    r"\b(definitely|certainly|clearly)\b.{0,30}\b(fraud\w*|scam\w*)\b|"
    r"\b(committed|committing)\b",
    re.IGNORECASE,
)


def validate_explanation(explanation: Explanation, evidence_ids: Collection[str]) -> None:
    """Explanations cite real evidence ids and never assert guilt."""
    unknown = set(explanation.cited_evidence_ids) - set(evidence_ids)
    if unknown:
        raise ContractViolation(f"explanation cites unknown evidence: {sorted(unknown)}")
    if _GUILT.search(explanation.text):
        raise ContractViolation("explanation asserts guilt")
