"""Payment state machine (pure). The only place that defines which transitions exist."""

from enum import StrEnum

from trustbank.contracts import TERMINAL_STATUSES, PaymentStatus


class Event(StrEnum):
    ASSESS = "ASSESS"
    ELEVATED = "ELEVATED"  # pre-score at or above the elevated threshold: ask questions
    CLEARED = "CLEARED"  # policy action PROCEED
    REQUIRE_REVIEW = "REQUIRE_REVIEW"  # policy action REVIEW
    REQUIRE_HOLD = "REQUIRE_HOLD"  # policy action HOLD
    ANSWERS = "ANSWERS"
    ACKNOWLEDGE = "ACKNOWLEDGE"
    EXPIRE = "EXPIRE"
    CONTINUE = "CONTINUE"
    AUTHORIZE = "AUTHORIZE"
    CANCEL = "CANCEL"


S = PaymentStatus

# ANSWERS moves QUESTIONNAIRE to ASSESSING while answers are interpreted, which also blocks a
# concurrent second submission; policy then picks READY_FOR_AUTH, REVIEW or HOLD_ACTIVE.
_TRANSITIONS: dict[tuple[PaymentStatus, Event], PaymentStatus] = {
    (S.INITIATED, Event.ASSESS): S.ASSESSING,
    (S.ASSESSING, Event.ELEVATED): S.QUESTIONNAIRE,
    (S.ASSESSING, Event.CLEARED): S.READY_FOR_AUTH,
    (S.ASSESSING, Event.REQUIRE_REVIEW): S.REVIEW,
    (S.ASSESSING, Event.REQUIRE_HOLD): S.HOLD_ACTIVE,
    (S.QUESTIONNAIRE, Event.ANSWERS): S.ASSESSING,
    (S.REVIEW, Event.ACKNOWLEDGE): S.READY_FOR_AUTH,
    (S.HOLD_ACTIVE, Event.EXPIRE): S.HOLD_EXPIRED,
    (S.HOLD_EXPIRED, Event.CONTINUE): S.READY_FOR_AUTH,
    (S.READY_FOR_AUTH, Event.AUTHORIZE): S.COMPLETED,
}


class InvalidTransitionError(Exception):
    def __init__(self, status: PaymentStatus, event: Event) -> None:
        super().__init__(f"{event} is not allowed in {status}")
        self.status = status
        self.event = event


def next_status(status: PaymentStatus, event: Event) -> PaymentStatus:
    if event is Event.CANCEL and status not in TERMINAL_STATUSES:
        return S.CANCELLED
    target = _TRANSITIONS.get((status, event))
    if target is None:
        raise InvalidTransitionError(status, event)
    return target


def available_actions(status: PaymentStatus, *, verified: bool) -> list[str]:
    """Customer actions valid right now (HOLD_ACTIVE never offers CONTINUE or AUTHORIZE)."""
    if status in TERMINAL_STATUSES:
        return []
    by_status: dict[PaymentStatus, list[str]] = {
        S.QUESTIONNAIRE: ["ANSWER"],
        S.REVIEW: ["ACKNOWLEDGE"],
        S.READY_FOR_AUTH: ["AUTHORIZE"],
        S.HOLD_EXPIRED: ["CONTINUE"] if verified else ["VERIFY"],
    }
    return [*by_status.get(status, []), "CANCEL"]
