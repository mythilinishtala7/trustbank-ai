"""Agent 1: transaction anomaly detector (deterministic ADK custom agent).

Compares a payment with the customer's own history. It never treats a new recipient or a short
history as high risk by itself, and it never sees scenario labels.
"""

import asyncio
import statistics
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import datetime, timedelta

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions
from pydantic import ConfigDict

from trustbank.agents.contracts import (
    AgentFinding,
    AgentId,
    ContractViolation,
    Evidence,
    validate_grounding,
)
from trustbank.agents.trace import ToolRecorder
from trustbank.domain import Provenance, Transaction
from trustbank.store import DatasetRepository

AGENT_ID: AgentId = "anomaly"
AGENT_NAME = "anomaly_detector"
STATE_INPUT = "payment_input"
STATE_FINDING = "anomaly_finding"
STATE_TRACE = "anomaly_trace"

LOW_HISTORY = 5  # fewer earlier payments than this lowers confidence and caps the score
SCORE_CAP_LOW_HISTORY = 29  # stays under the elevated threshold unless the amount is extreme
EXTREME_BALANCE_SHARE = 0.5
UNUSUAL_HOUR_GAP = 8  # hours away from the usual payment hour (circular)
BURST_WINDOW = timedelta(hours=24)
_V = Provenance.VERIFIED_SYNTHETIC


@dataclass(frozen=True)
class PaymentInput:
    customer_id: str
    beneficiary_id: str
    amount: int
    as_of: datetime

    @classmethod
    def from_state(cls, raw: dict[str, object]) -> "PaymentInput":
        return cls(
            customer_id=str(raw["customer_id"]),
            beneficiary_id=str(raw["beneficiary_id"]),
            amount=int(str(raw["amount"])),
            as_of=datetime.fromisoformat(str(raw["as_of"])),
        )


@dataclass(frozen=True)
class History:
    customer_id: str
    account_id: str
    balance: int
    transactions: tuple[Transaction, ...]  # before as_of, newest first


class AnomalyTools:
    """Statistical tools over the customer's Firestore history. Every call is recorded."""

    def __init__(self, repo: DatasetRepository, recorder: ToolRecorder) -> None:
        self._repo, self._rec = repo, recorder

    def load_history(self, customer_id: str, as_of: datetime) -> History:
        customer = self._repo.get_customer(customer_id)
        account = self._repo.account_for_owner(customer_id) if customer else None
        if customer is None or account is None:
            raise LookupError("customer or account not found")
        txns = tuple(
            t for t in self._repo.transactions_from_account(account.id) if t.timestamp < as_of
        )
        self._rec.record(
            "load_history",
            {"customer_id": customer_id, "as_of": as_of.isoformat()},
            f"{len(txns)} earlier payments, balance {customer.balance}",
            {customer_id, account.id, *(t.id for t in txns), *(t.beneficiary_id for t in txns)},
        )
        return History(customer_id, account.id, customer.balance, txns)

    def amount_profile(self, h: History, amount: int) -> Evidence | None:
        amounts = [t.amount for t in h.transactions]
        if not amounts:
            self._rec.record("amount_profile", {"amount": amount}, "no history")
            return None
        top = max(h.transactions, key=lambda t: t.amount)
        ratio = amount / top.amount
        typical = statistics.median(amounts)
        points = _ratio_points(ratio)
        z = None
        if len(amounts) >= LOW_HISTORY and amount > top.amount:
            median = statistics.median(amounts)
            mad = statistics.median(abs(a - median) for a in amounts)
            sigma = max(1.4826 * mad, 0.1 * median, 1.0)
            z = (amount - median) / sigma
            points = max(points, _z_points(z))
        self._rec.record(
            "amount_profile",
            {"amount": amount},
            f"largest {top.amount}, ratio {ratio:.2f}"
            + (f", robust z {z:.1f}" if z is not None else "")
            + f", points {points}",
        )
        if points == 0:
            return None
        return Evidence(
            id="anomaly.amount_vs_history",
            summary=(
                f"Rs {amount:,} is {ratio:.1f} times the largest of the last {len(amounts)} "
                f"payments (Rs {top.amount:,}) and {amount / typical:.1f} times a typical "
                f"payment (Rs {typical:,.0f})."
            ),
            provenance=_V,
            source_entity_ids=(h.account_id, top.id),
            points=points,
        )

    def recipient_familiarity(self, h: History, beneficiary_id: str) -> Evidence | None:
        prior = [t for t in h.transactions if t.beneficiary_id == beneficiary_id]
        self._rec.record(
            "recipient_familiarity",
            {"beneficiary_id": beneficiary_id},
            f"{len(prior)} earlier payments to this recipient",
        )
        if prior:
            return None
        return Evidence(
            id="anomaly.new_recipient",
            summary="You have not paid this recipient before.",
            provenance=_V,
            source_entity_ids=(beneficiary_id,),
            points=10,
        )

    def recent_burst(self, h: History, as_of: datetime) -> Evidence | None:
        recent = [t for t in h.transactions if as_of - t.timestamp <= BURST_WINDOW]
        points = 25 if len(recent) >= 5 else 15 if len(recent) >= 3 else 0
        self._rec.record(
            "recent_burst", {"window_hours": 24}, f"{len(recent)} payments, points {points}"
        )
        if points == 0:
            return None
        return Evidence(
            id="anomaly.payment_burst",
            summary=f"{len(recent)} payments were made in the last 24 hours.",
            provenance=_V,
            source_entity_ids=tuple(t.id for t in recent),
            points=points,
        )

    def time_of_day(self, h: History, as_of: datetime) -> Evidence | None:
        if len(h.transactions) < LOW_HISTORY:
            self._rec.record("time_of_day", {}, "history too short")
            return None
        usual = statistics.median(t.timestamp.hour for t in h.transactions)
        gap = abs(as_of.hour - usual)
        gap = min(gap, 24 - gap)
        self._rec.record("time_of_day", {"hour": as_of.hour}, f"usual hour {usual}, gap {gap}")
        if gap < UNUSUAL_HOUR_GAP:
            return None
        return Evidence(
            id="anomaly.unusual_time",
            summary="This payment is at a different time of day from your usual payments.",
            provenance=_V,
            source_entity_ids=(h.account_id,),
            points=10,
        )

    def balance_share(self, h: History, amount: int) -> tuple[Evidence | None, bool]:
        """Returns the evidence and whether the amount is extreme relative to the balance."""
        share = amount / h.balance if h.balance > 0 else 1.0
        extreme = share >= EXTREME_BALANCE_SHARE
        points = 25 if extreme else 10 if share >= 0.25 else 0
        self._rec.record(
            "balance_share", {"amount": amount}, f"{share:.0%} of balance, points {points}"
        )
        if points == 0:
            return None, extreme
        return (
            Evidence(
                id="anomaly.balance_share",
                summary=f"This payment is {min(share, 1):.0%} of your current balance.",
                provenance=_V,
                source_entity_ids=(h.customer_id,),
                points=points,
            ),
            extreme,
        )


def _ratio_points(ratio: float) -> int:
    return (
        50 if ratio >= 8 else 35 if ratio >= 4 else 20 if ratio >= 2 else 10 if ratio >= 1.5 else 0
    )


def _z_points(z: float) -> int:
    return 60 if z >= 10 else 40 if z >= 6 else 25 if z >= 3.5 else 0


def assess_anomaly(
    repo: DatasetRepository, payment: PaymentInput, recorder: ToolRecorder | None = None
) -> tuple[AgentFinding, ToolRecorder]:
    rec = recorder or ToolRecorder(AGENT_ID)
    tools = AnomalyTools(repo, rec)
    h = tools.load_history(payment.customer_id, payment.as_of)
    share_ev, extreme = tools.balance_share(h, payment.amount)
    found = [
        tools.amount_profile(h, payment.amount),
        tools.recipient_familiarity(h, payment.beneficiary_id),
        tools.recent_burst(h, payment.as_of),
        tools.time_of_day(h, payment.as_of),
        share_ev,
    ]
    evidence = [e for e in found if e is not None]
    n = len(h.transactions)
    score = min(100, sum(e.points for e in evidence))
    if n < LOW_HISTORY:
        evidence.append(
            Evidence(
                id="anomaly.limited_history",
                summary=f"Only {n} earlier payments, so this check is less certain.",
                provenance=_V,
                source_entity_ids=(h.account_id,),
                points=0,
            )
        )
        if not extreme:
            score = min(score, SCORE_CAP_LOW_HISTORY)
        confidence = round(0.3 + 0.05 * n, 2)
    else:
        confidence = round(min(0.95, 0.6 + 0.02 * n), 2)
    finding = AgentFinding(
        agent_id=AGENT_ID,
        status="OK",
        score=score,
        confidence=confidence,
        evidence=tuple(evidence),
    )
    validate_grounding(finding, rec.entity_ids | {payment.beneficiary_id})
    return finding, rec


class AnomalyAgent(BaseAgent):
    """ADK custom agent. Reads `payment_input` from session state; writes finding and trace."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    repo: DatasetRepository

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        recorder = ToolRecorder(AGENT_ID)
        try:
            payment = PaymentInput.from_state(ctx.session.state[STATE_INPUT])
            finding, _ = await asyncio.to_thread(assess_anomaly, self.repo, payment, recorder)
        except (ContractViolation, LookupError, KeyError, ValueError) as exc:
            finding = AgentFinding.failed(AGENT_ID, f"{type(exc).__name__}: {exc}")
        except Exception as exc:  # any tool failure must fail safe, never crash the payment
            finding = AgentFinding.failed(AGENT_ID, f"{type(exc).__name__}")
        yield Event(
            author=self.name,
            actions=EventActions(
                state_delta={
                    STATE_FINDING: finding.model_dump(mode="json"),
                    STATE_TRACE: [c.model_dump(mode="json") for c in recorder.calls],
                }
            ),
        )


def build_anomaly_agent(repo: DatasetRepository) -> AnomalyAgent:
    return AnomalyAgent(
        name=AGENT_NAME,
        description="Compares a payment with the customer's own history. No LLM.",
        repo=repo,
    )
