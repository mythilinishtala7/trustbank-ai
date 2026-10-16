"""Customer-facing whitelist model. Nothing else may be returned from customer endpoints."""

from datetime import datetime

from trustbank.contracts import ApiModel, PaymentStatus
from trustbank.payments.models import PaymentDoc
from trustbank.payments.state import available_actions

_EXPLAINED = frozenset(
    {
        PaymentStatus.QUESTIONNAIRE,
        PaymentStatus.REVIEW,
        PaymentStatus.HOLD_ACTIVE,
        PaymentStatus.HOLD_EXPIRED,
    }
)
_HOLD_STATUSES = frozenset({PaymentStatus.HOLD_ACTIVE, PaymentStatus.HOLD_EXPIRED})


class CustomerRecipient(ApiModel):
    display_name: str | None
    handle: str
    verified: bool


class CustomerOption(ApiModel):
    value: str
    label: str


class CustomerQuestion(ApiModel):
    id: str
    text: str
    options: list[CustomerOption]
    allow_free_text: bool


class CustomerPayment(ApiModel):
    id: str
    status: PaymentStatus
    recipient: CustomerRecipient
    amount: int
    note: str
    created_at: datetime
    server_time: datetime
    explanation: str | None
    reasons: list[str]
    questions: list[CustomerQuestion]
    hold_until: datetime | None
    verified: bool
    actions: list[str]
    simulated: bool = True


def to_customer_payment(doc: PaymentDoc, server_time: datetime) -> CustomerPayment:
    explained = doc.explanation is not None and doc.status in _EXPLAINED
    questions = (
        [
            CustomerQuestion(
                id=q.id,
                text=q.text,
                options=[CustomerOption(value=o.value, label=o.label) for o in q.options],
                allow_free_text=q.allow_free_text,
            )
            for q in doc.questions[:3]
        ]
        if doc.status is PaymentStatus.QUESTIONNAIRE
        else []
    )
    return CustomerPayment(
        id=doc.id,
        status=doc.status,
        recipient=CustomerRecipient(
            display_name=doc.recipient_name,
            handle=doc.recipient_handle,
            verified=doc.recipient_verified,
        ),
        amount=doc.amount,
        note=doc.note,
        created_at=doc.created_at,
        server_time=server_time,
        explanation=doc.explanation.text if explained and doc.explanation else None,
        reasons=list(doc.explanation.reasons) if explained and doc.explanation else [],
        questions=questions,
        hold_until=doc.hold_until if doc.status in _HOLD_STATUSES else None,
        verified=doc.verified if doc.status is PaymentStatus.HOLD_EXPIRED else False,
        actions=available_actions(doc.status, verified=doc.verified),
    )
