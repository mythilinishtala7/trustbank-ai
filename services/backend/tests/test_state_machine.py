import pytest

from trustbank.contracts import TERMINAL_STATUSES, PaymentStatus
from trustbank.payments.state import Event, InvalidTransitionError, available_actions, next_status

S = PaymentStatus

VALID = [
    (S.INITIATED, Event.ASSESS, S.ASSESSING),
    (S.ASSESSING, Event.CLEARED, S.READY_FOR_AUTH),
    (S.ASSESSING, Event.ELEVATED, S.QUESTIONNAIRE),
    (S.ASSESSING, Event.REQUIRE_REVIEW, S.REVIEW),
    (S.ASSESSING, Event.REQUIRE_HOLD, S.HOLD_ACTIVE),
    (S.QUESTIONNAIRE, Event.ANSWERS, S.ASSESSING),
    (S.REVIEW, Event.ACKNOWLEDGE, S.READY_FOR_AUTH),
    (S.HOLD_ACTIVE, Event.EXPIRE, S.HOLD_EXPIRED),
    (S.HOLD_EXPIRED, Event.CONTINUE, S.READY_FOR_AUTH),
    (S.READY_FOR_AUTH, Event.AUTHORIZE, S.COMPLETED),
]


@pytest.mark.parametrize(("status", "event", "target"), VALID)
def test_valid_transitions(status: PaymentStatus, event: Event, target: PaymentStatus) -> None:
    assert next_status(status, event) is target


def test_every_other_transition_is_rejected() -> None:
    allowed = {(s, e) for s, e, _ in VALID}
    for status in PaymentStatus:
        for event in Event:
            if event is Event.CANCEL and status not in TERMINAL_STATUSES:
                continue
            if (status, event) in allowed:
                continue
            with pytest.raises(InvalidTransitionError):
                next_status(status, event)


@pytest.mark.parametrize("status", [s for s in PaymentStatus if s not in TERMINAL_STATUSES])
def test_cancel_from_any_non_terminal(status: PaymentStatus) -> None:
    assert next_status(status, Event.CANCEL) is S.CANCELLED


@pytest.mark.parametrize("status", sorted(TERMINAL_STATUSES))
def test_terminal_states_are_final(status: PaymentStatus) -> None:
    for event in Event:
        with pytest.raises(InvalidTransitionError):
            next_status(status, event)


def test_hold_active_never_reaches_authorization() -> None:
    assert S.HOLD_ACTIVE not in {s for s, e, _ in VALID if e in {Event.CONTINUE, Event.AUTHORIZE}}
    assert "AUTHORIZE" not in available_actions(S.HOLD_ACTIVE, verified=True)
    assert "CONTINUE" not in available_actions(S.HOLD_ACTIVE, verified=True)
    assert available_actions(S.HOLD_ACTIVE, verified=False) == ["CANCEL"]


def test_actions_by_status() -> None:
    assert available_actions(S.QUESTIONNAIRE, verified=False) == ["ANSWER", "CANCEL"]
    assert available_actions(S.REVIEW, verified=False) == ["ACKNOWLEDGE", "CANCEL"]
    assert available_actions(S.HOLD_EXPIRED, verified=False) == ["VERIFY", "CANCEL"]
    assert available_actions(S.HOLD_EXPIRED, verified=True) == ["CONTINUE", "CANCEL"]
    assert available_actions(S.READY_FOR_AUTH, verified=False) == ["AUTHORIZE", "CANCEL"]
    assert available_actions(S.ASSESSING, verified=False) == ["CANCEL"]
    assert available_actions(S.COMPLETED, verified=False) == []
    assert available_actions(S.CANCELLED, verified=False) == []
