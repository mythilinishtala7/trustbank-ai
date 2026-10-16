"""Anomaly agent: statistics over the customer's own payment history. No LLM.

Newness and thin history are never risky on their own. With fewer than MIN_HISTORY payments the
score is capped below the elevated threshold unless the amount is extreme against the balance.
"""

import math
import statistics
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta
from typing import Any, Protocol

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from pydantic import BaseModel

from trustbank.agents.recorder import ToolRecorder
from trustbank.contracts import AgentFinding, Evidence, PaymentContext
from trustbank.domain import Account, Beneficiary, Customer, Provenance, Transaction

MIN_HISTORY = 5
LIMITED_CAP = 29  # one below the default elevated threshold
EXTREME_BALANCE_FRACTION = 0.8
HISTORY_LIMIT = 200


class HistoryReader(Protocol):
    def get_customer(self, customer_id: str) -> Customer | None: ...

    def get_beneficiary(self, beneficiary_id: str) -> Beneficiary | None: ...

    def account_for_owner(self, owner_id: str) -> Account | None: ...

    def transactions_from_account(self, account_id: str, limit: int = ...) -> list[Transaction]: ...


class AmountStats(BaseModel):
    count: int
    mean: float
    median: float
    maximum: int
    max_transaction_id: str | None
    ratio_to_mean: float | None
    ratio_to_max: float | None
    robust_z: float | None


class Familiarity(BaseModel):
    prior_payments: int
    last_transaction_id: str | None


class Frequency(BaseModel):
    last_hour: int
    last_24h: int
    daily_baseline: float
    transaction_ids: list[str]


class TimeShift(BaseModel):
    current_hour: int
    nearest_usual_hour: int | None
    distance_hours: int | None


def amount_deviation(history: list[Transaction], amount: int) -> AmountStats:
    amounts = [t.amount for t in history]
    if not amounts:
        return AmountStats(
            count=0,
            mean=0,
            median=0,
            maximum=0,
            max_transaction_id=None,
            ratio_to_mean=None,
            ratio_to_max=None,
            robust_z=None,
        )
    mean = statistics.fmean(amounts)
    median = statistics.median(amounts)
    top = max(history, key=lambda t: t.amount)
    z: float | None = None
    if len(amounts) >= MIN_HISTORY:
        mad = statistics.median(abs(a - median) for a in amounts)
        if mad > 0:
            z = 0.6745 * (amount - median) / mad
    return AmountStats(
        count=len(amounts),
        mean=mean,
        median=median,
        maximum=top.amount,
        max_transaction_id=top.id,
        ratio_to_mean=amount / mean if mean else None,
        ratio_to_max=amount / top.amount if top.amount else None,
        robust_z=z,
    )


def recipient_familiarity(history: list[Transaction], beneficiary_id: str) -> Familiarity:
    prior = [t for t in history if t.beneficiary_id == beneficiary_id]
    latest = max(prior, key=lambda t: t.timestamp).id if prior else None
    return Familiarity(prior_payments=len(prior), last_transaction_id=latest)


def frequency_burst(history: list[Transaction], now: datetime) -> Frequency:
    recent = [t for t in history if now - timedelta(hours=24) <= t.timestamp <= now]
    last_hour = [t for t in recent if t.timestamp >= now - timedelta(hours=1)]
    if history:
        span_days = max(1.0, (now - min(t.timestamp for t in history)).total_seconds() / 86400)
        baseline = len(history) / span_days
    else:
        baseline = 0.0
    return Frequency(
        last_hour=len(last_hour),
        last_24h=len(recent),
        daily_baseline=baseline,
        transaction_ids=[t.id for t in recent][:6],
    )


def time_of_day_shift(history: list[Transaction], now: datetime) -> TimeShift:
    hours = {t.timestamp.hour for t in history}
    if not hours:
        return TimeShift(current_hour=now.hour, nearest_usual_hour=None, distance_hours=None)

    def circular(a: int, b: int) -> int:
        d = abs(a - b)
        return min(d, 24 - d)

    nearest = min(hours, key=lambda h: circular(h, now.hour))
    return TimeShift(
        current_hour=now.hour,
        nearest_usual_hour=nearest,
        distance_hours=circular(nearest, now.hour),
    )


def _clamp(value: float, low: int, high: int) -> int:
    return max(low, min(high, round(value)))


def assess_anomaly(
    *,
    ctx: PaymentContext,
    history: list[Transaction],
    balance: int,
    stats: AmountStats,
    familiarity: Familiarity,
    frequency: Frequency,
    shift: TimeShift,
) -> AgentFinding:
    evidence: list[Evidence] = []
    enough = stats.count >= MIN_HISTORY

    if stats.ratio_to_max is not None and stats.ratio_to_max > 1:
        points = _clamp(15 * math.log2(stats.ratio_to_max), 0, 70)
        if stats.robust_z is not None and stats.robust_z >= 3.5:
            points = min(70, points + 5)
        if points:
            z = f", robust z {stats.robust_z:.1f}" if stats.robust_z is not None else ""
            evidence.append(
                Evidence(
                    id="anomaly.amount_deviation",
                    summary=(
                        f"Amount {ctx.amount} is {stats.ratio_to_max:.1f}x the largest of "
                        f"{stats.count} prior payments (max {stats.maximum}, mean "
                        f"{stats.mean:.0f}{z})."
                    ),
                    provenance=Provenance.INFERRED,
                    source_entity_ids=[stats.max_transaction_id]
                    if stats.max_transaction_id
                    else [],
                    points=points,
                )
            )

    fraction = ctx.amount / balance if balance > 0 else 1.0
    if fraction > 0.2:
        evidence.append(
            Evidence(
                id="anomaly.large_vs_balance",
                summary=f"Amount is {fraction:.0%} of the available balance.",
                provenance=Provenance.INFERRED,
                source_entity_ids=[ctx.customer_id],
                points=_clamp((fraction - 0.2) * 50, 0, 25),
            )
        )

    if familiarity.prior_payments == 0:
        evidence.append(
            Evidence(
                id="anomaly.new_recipient",
                summary="First payment to this recipient.",
                provenance=Provenance.INFERRED,
                source_entity_ids=[ctx.beneficiary_id],
                points=5,
            )
        )
    else:
        evidence.append(
            Evidence(
                id="anomaly.known_recipient",
                summary=f"{familiarity.prior_payments} earlier payments to this recipient.",
                provenance=Provenance.INFERRED,
                source_entity_ids=[ctx.beneficiary_id]
                + ([familiarity.last_transaction_id] if familiarity.last_transaction_id else []),
                points=0,
            )
        )

    if frequency.last_24h >= 3 and frequency.last_24h >= 3 * max(frequency.daily_baseline, 0.5):
        evidence.append(
            Evidence(
                id="anomaly.burst_activity",
                summary=(
                    f"{frequency.last_24h} payments in 24 hours ({frequency.last_hour} in the "
                    f"last hour) against a usual {frequency.daily_baseline:.1f} per day."
                ),
                provenance=Provenance.INFERRED,
                source_entity_ids=frequency.transaction_ids,
                points=_clamp(8 + 4 * (frequency.last_24h - 3), 0, 20),
            )
        )

    if enough and shift.distance_hours is not None and shift.distance_hours >= 6:
        evidence.append(
            Evidence(
                id="anomaly.unusual_time",
                summary=(
                    f"Payment hour {shift.current_hour}:00 is {shift.distance_hours} hours from "
                    f"the nearest usual hour ({shift.nearest_usual_hour}:00)."
                ),
                provenance=Provenance.INFERRED,
                points=4,
            )
        )

    score = min(100, sum(e.points for e in evidence))
    if not enough:
        extreme = fraction >= EXTREME_BALANCE_FRACTION
        evidence.append(
            Evidence(
                id="anomaly.limited_history",
                summary=(
                    f"Only {stats.count} prior payments, so statistical comparison is weak"
                    + ("." if extreme else "; score is capped below the elevated level.")
                ),
                provenance=Provenance.INFERRED,
                points=0,
            )
        )
        if not extreme:
            score = min(score, LIMITED_CAP)
        confidence = min(0.5, 0.3 + 0.1 * stats.count)
    else:
        confidence = min(0.95, 0.6 + 0.02 * stats.count)
    return AgentFinding(
        agent_id="anomaly",
        status="OK",
        score=score,
        confidence=round(confidence, 2),
        evidence=evidence,
    )


class AnomalyAgent(BaseAgent):
    """Custom ADK agent; reads the payment from session state and writes its finding back."""

    recorder: Any
    history: Any

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        payment = PaymentContext.model_validate(ctx.session.state["payment"])
        recorder: ToolRecorder = self.recorder
        repo: HistoryReader = self.history
        agent = "anomaly"

        customer = await recorder.call(
            agent,
            "load_customer",
            {"customer_id": payment.customer_id},
            lambda: repo.get_customer(payment.customer_id),
            lambda c: "customer found" if c else "customer not found",
        )
        account = await recorder.call(
            agent,
            "load_account",
            {"owner_id": payment.customer_id},
            lambda: repo.account_for_owner(payment.customer_id),
            lambda a: "account found" if a else "account not found",
        )
        if customer is None or account is None:
            raise LookupError("customer or account not found")
        history = await recorder.call(
            agent,
            "load_history",
            {"account_id": account.id, "limit": HISTORY_LIMIT},
            lambda: repo.transactions_from_account(account.id, HISTORY_LIMIT),
            lambda h: f"{len(h)} prior payments",
        )
        stats = await recorder.call(
            agent,
            "amount_deviation",
            {"amount": payment.amount},
            lambda: amount_deviation(history, payment.amount),
            lambda s: (
                f"max {s.maximum}, mean {s.mean:.0f}, ratio to max "
                + (f"{s.ratio_to_max:.2f}" if s.ratio_to_max is not None else "n/a")
            ),
        )
        familiarity = await recorder.call(
            agent,
            "recipient_familiarity",
            {"beneficiary_id": payment.beneficiary_id},
            lambda: recipient_familiarity(history, payment.beneficiary_id),
            lambda f: f"{f.prior_payments} prior payments to recipient",
        )
        frequency = await recorder.call(
            agent,
            "frequency_burst",
            {"as_of": payment.now.isoformat()},
            lambda: frequency_burst(history, payment.now),
            lambda f: f"{f.last_24h} payments in 24h, baseline {f.daily_baseline:.1f}/day",
        )
        shift = await recorder.call(
            agent,
            "time_of_day_shift",
            {"as_of": payment.now.isoformat()},
            lambda: time_of_day_shift(history, payment.now),
            lambda s: f"hour {s.current_hour}, {s.distance_hours} h from usual",
        )
        finding = assess_anomaly(
            ctx=payment,
            history=history,
            balance=customer.balance,
            stats=stats,
            familiarity=familiarity,
            frequency=frequency,
            shift=shift,
        )
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"finding": finding.model_dump(mode="json")}),
        )
