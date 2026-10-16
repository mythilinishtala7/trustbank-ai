"""Anomaly agent: statistics over a customer's own history (in-memory, no services needed)."""

import asyncio
import time
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from tests.support_llm import scripted
from trustbank.agents.anomaly import (
    LIMITED_CAP,
    amount_deviation,
    assess_anomaly,
    frequency_burst,
    recipient_familiarity,
    time_of_day_shift,
)
from trustbank.agents.orchestrator import AdkOrchestrator
from trustbank.contracts import AgentFinding, PaymentContext
from trustbank.domain import Account, Customer, OwnerType, Transaction
from trustbank.graph import GraphService

NOW = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)


def txn(
    i: int, amount: int, *, days_ago: float = 10, to: str = "ben_a", hour: int = 12
) -> Transaction:
    when = (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0)
    return Transaction(
        id=f"t{i}",
        source_account_id="acct_c",
        beneficiary_id=to,
        amount=amount,
        note="n",
        timestamp=when,
    )


def history(amounts: list[int], to: str = "ben_a", hour: int = 12) -> list[Transaction]:
    return [txn(i, a, days_ago=5 + 3 * i, to=to, hour=hour) for i, a in enumerate(amounts)]


def assess(
    past: list[Transaction],
    amount: int,
    to: str = "ben_new",
    balance: int = 100_000,
    now: datetime = NOW,
) -> AgentFinding:
    ctx = PaymentContext(payment_id="p", customer_id="c", beneficiary_id=to, amount=amount, now=now)
    return assess_anomaly(
        ctx=ctx,
        history=past,
        balance=balance,
        stats=amount_deviation(past, amount),
        familiarity=recipient_familiarity(past, to),
        frequency=frequency_burst(past, now),
        shift=time_of_day_shift(past, now),
    )


def ids(f: AgentFinding) -> dict[str, int]:
    return {e.id: e.points for e in f.evidence}


def test_routine_payment_scores_zero() -> None:
    f = assess(history([1000, 1200, 900, 1100, 1000, 1300]), 1100, to="ben_a")
    assert f.score == 0 and f.status == "OK"
    assert ids(f)["anomaly.known_recipient"] == 0


def test_large_deviation_uses_ratio_and_robust_z() -> None:
    f = assess(history([1000, 1200, 900, 1100, 1000, 1300, 1050]), 30_000, to="ben_a")
    e = next(e for e in f.evidence if e.id == "anomaly.amount_deviation")
    assert e.points >= 60 and "robust z" in e.summary and f.score >= 60
    assert f.confidence > 0.6


def test_new_recipient_alone_is_a_tiny_signal() -> None:
    f = assess(history([1000, 1200, 900, 1100, 1000, 1300]), 1000)
    assert f.score == 5 and ids(f) == {"anomaly.new_recipient": 5}


def test_limited_history_is_capped_below_elevated_with_low_confidence() -> None:
    f = assess(history([500, 700]), 8_000, balance=100_000)
    assert f.score == LIMITED_CAP < 30
    assert f.confidence < 0.6
    assert "anomaly.limited_history" in ids(f)


def test_no_history_at_all_is_not_a_risk() -> None:
    f = assess([], 600)
    assert f.score <= 5 and f.confidence <= 0.4


def test_limited_history_does_not_hide_an_extreme_amount_against_balance() -> None:
    f = assess(history([500, 700]), 90_000, balance=100_000)
    assert f.score > LIMITED_CAP


def test_large_share_of_balance_adds_points() -> None:
    low = assess(history([1000] * 6), 1000, to="ben_a", balance=100_000)
    high = assess(history([1000] * 6), 1000, to="ben_a", balance=2_000)
    assert "anomaly.large_vs_balance" in ids(high) and "anomaly.large_vs_balance" not in ids(low)


def test_burst_activity_is_detected() -> None:
    recent = [txn(100 + i, 800, days_ago=i / 48) for i in range(4)]
    f = assess(history([1000] * 6) + recent, 800, to="ben_a")
    assert ids(f).get("anomaly.burst_activity", 0) > 0


def test_time_of_day_shift_needs_enough_history() -> None:
    night = NOW.replace(hour=2)
    enough = assess(history([1000] * 6, hour=14), 1000, to="ben_a", now=night)
    thin = assess(history([1000] * 3, hour=14), 1000, to="ben_a", now=night)
    assert ids(enough).get("anomaly.unusual_time") == 4
    assert "anomaly.unusual_time" not in ids(thin)


def test_statistics_helpers() -> None:
    stats = amount_deviation(history([100, 200, 300, 400, 500]), 1000)
    assert stats.maximum == 500 and stats.ratio_to_max == 2.0 and stats.ratio_to_mean == 1000 / 300
    assert stats.robust_z is not None and stats.robust_z > 3.5
    assert amount_deviation(history([100, 200]), 1000).robust_z is None
    assert recipient_familiarity(history([100, 200], to="x"), "x").prior_payments == 2


class _Reader:
    def __init__(self, past: list[Transaction], delay: float = 0.0, fail: bool = False) -> None:
        self._past, self._delay, self._fail = past, delay, fail

    def get_customer(self, customer_id: str) -> Customer:
        return Customer(id=customer_id, display_name="X", handle="x", balance=50_000)

    def get_beneficiary(self, beneficiary_id: str) -> None:
        return None

    def account_for_owner(self, owner_id: str) -> Account:
        return Account(
            id="acct_c", owner_id=owner_id, owner_type=OwnerType.CUSTOMER, opened_at=NOW,
            masked_number="1234",
        )  # fmt: skip

    def transactions_from_account(self, account_id: str, limit: int = 200) -> list[Transaction]:
        time.sleep(self._delay)
        if self._fail:
            raise ConnectionError("store unavailable")
        return self._past


class _Graph:
    def account_for_owner(self, owner_id: str) -> None:
        return None


class Sink:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def emit(self, agent_id: str, type: str, message: str, **kw: Any) -> None:
        self.events.append((agent_id, type, kw))


def run(reader: _Reader, detector_timeout: float = 5.0) -> tuple[Any, Sink]:
    orch = AdkOrchestrator(
        model=scripted(),
        graph=cast(GraphService, _Graph()),
        history=reader,
        detector_timeout=detector_timeout,
    )
    ctx = PaymentContext(payment_id="p", customer_id="c", beneficiary_id="b", amount=900, now=NOW)
    sink = Sink()
    return asyncio.run(orch.run_detectors(ctx, sink)), sink


def test_detector_failure_is_recorded_and_the_other_detector_still_reports() -> None:
    result, sink = run(_Reader(history([1000] * 6), fail=True))
    assert result.anomaly.status == "FAILED" and "ConnectionError" in (result.anomaly.error or "")
    assert result.fraud_network.status == "OK"
    assert ("anomaly", "FAILED") in {(a, t) for a, t, _ in sink.events}
    assert ("orchestrator", "FAILED") in {(a, t) for a, t, _ in sink.events}


def test_detector_timeout_is_recorded() -> None:
    orch = AdkOrchestrator(
        model=scripted(),
        graph=cast(GraphService, _Graph()),
        history=_Reader(history([1000] * 6), delay=1.0),
        detector_timeout=0.1,
    )
    ctx = PaymentContext(payment_id="p", customer_id="c", beneficiary_id="b", amount=900, now=NOW)

    async def timed() -> tuple[Any, float]:
        started = time.perf_counter()
        result = await orch.run_detectors(ctx, Sink())
        return result, time.perf_counter() - started

    result, elapsed = asyncio.run(timed())
    assert elapsed < 0.9
    assert result.anomaly.status == "TIMEOUT" and result.anomaly.score == 0
    assert result.fraud_network.status == "OK"


def test_successful_run_records_tool_calls() -> None:
    result, sink = run(_Reader(history([1000] * 6)))
    tools = [c.tool for c in result.tool_calls if c.agent_id == "anomaly"]
    assert tools == [
        "load_customer", "load_account", "load_history", "amount_deviation",
        "recipient_familiarity", "frequency_burst", "time_of_day_shift",
    ]  # fmt: skip
    assert any(t == "TOOL_CALL" for _, t, _ in sink.events)
