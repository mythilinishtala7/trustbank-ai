"""Fraud-network agent: behavioural indicators from graph queries. No LLM.

Indicators are INFERRED from flow behaviour only. Names, labels and account age alone never score.
Two independent indicator groups are needed to reach the elevated range on network evidence alone.
"""

from collections.abc import AsyncGenerator
from datetime import datetime
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events import Event, EventActions

from trustbank.agents.recorder import ToolRecorder
from trustbank.contracts import AgentFinding, Evidence, PaymentContext
from trustbank.domain import Provenance
from trustbank.graph import GraphService
from trustbank.graph.results import FlowProfile, ForwardingChains, NeighborsResult, SenderSummary

LONG_WINDOW_HOURS = 168
BURST_WINDOW_HOURS = 72
MAX_GAP_MINUTES = 15
MAX_HOPS = 3
YOUNG_DAYS = 90
RAPID_DWELL_MINUTES = 30
RAPID_RETENTION = 0.25
RAPID_MIN_FORWARDS = 3
FAN_IN_MIN_SENDERS = 5
VELOCITY_MIN_TXNS = 12
SINGLE_GROUP_CAP = 40

POINTS = {
    "network.rapid_pass_through": 20,
    "network.multi_hop_layering": 14,
    "network.fan_in_burst": 8,
    "network.high_velocity": 4,
}
# Volume indicators share one group: they are not independent of each other.
GROUPS = {
    "network.rapid_pass_through": "dwell",
    "network.multi_hop_layering": "structure",
    "network.fan_in_burst": "volume",
    "network.high_velocity": "volume",
}


def _minutes(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.0f} min" if value >= 10 else f"{value:.1f} min"


def assess_network(
    *,
    beneficiary_id: str,
    account_id: str,
    age_days: int | None,
    senders: SenderSummary,
    flow_long: FlowProfile,
    flow_short: FlowProfile,
    chains: ForwardingChains,
    connections: NeighborsResult,
) -> AgentFinding:
    young = age_days is not None and age_days <= YOUNG_DAYS
    evidence: list[Evidence] = []
    cleared: list[Evidence] = []

    forwards = flow_long.outbound_count
    rapid = (
        forwards >= RAPID_MIN_FORWARDS
        and flow_long.median_dwell_minutes is not None
        and flow_long.median_dwell_minutes <= RAPID_DWELL_MINUTES
        and flow_long.retention_ratio is not None
        and flow_long.retention_ratio <= RAPID_RETENTION
    )
    if rapid:
        retained = flow_long.retention_ratio or 0.0
        evidence.append(
            Evidence(
                id="network.rapid_pass_through",
                summary=(
                    f"{forwards} forwards in {LONG_WINDOW_HOURS} h; median dwell "
                    f"{_minutes(flow_long.median_dwell_minutes)}, {retained:.0%} of inflow "
                    f"retained, {flow_long.distinct_destinations} destination(s)."
                ),
                provenance=Provenance.INFERRED,
                source_entity_ids=[account_id, *flow_long.outbound_transaction_ids[:6]],
                points=POINTS["network.rapid_pass_through"],
            )
        )
    elif forwards > 0 and flow_long.median_dwell_minutes is not None:
        retention = flow_long.retention_ratio
        outflow = flow_long.outflow_ratio
        detail = (
            f"median dwell {_minutes(flow_long.median_dwell_minutes)}, "
            f"{retention:.0%} retained, single hop"
            if retention is not None
            else f"median dwell {_minutes(flow_long.median_dwell_minutes)}"
        )
        schedule = ", forwards on a regular schedule" if flow_long.regular_schedule else ""
        if flow_long.median_dwell_minutes > RAPID_DWELL_MINUTES:
            cleared.append(
                Evidence(
                    id="network.long_dwell_cleared",
                    summary=f"Funds are held before moving on: {detail}{schedule}.",
                    provenance=Provenance.INFERRED,
                    source_entity_ids=[account_id],
                )
            )
        if outflow is not None and outflow >= 0.8:
            cleared.append(
                Evidence(
                    id="network.high_pass_through_cleared",
                    summary=(
                        f"{outflow:.0%} of inflow moves on but not rapidly: {detail}{schedule}."
                    ),
                    provenance=Provenance.INFERRED,
                    source_entity_ids=[account_id],
                )
            )

    layered = [c for c in chains.chains if len(c.hops) >= 2 and not c.terminal_has_onward]
    if len(layered) >= 2:
        deepest = max(layered, key=lambda c: len(c.hops))
        timings = ", ".join(
            f"hop {i + 1}: {_minutes(h.gap_minutes)}" for i, h in enumerate(deepest.hops)
        )
        evidence.append(
            Evidence(
                id="network.multi_hop_layering",
                summary=(
                    f"{len(layered)} forwarding chains of up to {len(deepest.hops)} hops, each "
                    f"hop within {MAX_GAP_MINUTES} min ({timings}); funds end with no onward move."
                ),
                provenance=Provenance.INFERRED,
                source_entity_ids=[
                    account_id,
                    *(h.transaction_id for h in deepest.hops),
                    deepest.terminal_account_id,
                ],
                points=POINTS["network.multi_hop_layering"],
            )
        )

    if (
        young
        and senders.distinct_senders >= FAN_IN_MIN_SENDERS
        and senders.distinct_senders >= 3 * max(1, flow_short.distinct_destinations)
    ):
        evidence.append(
            Evidence(
                id="network.fan_in_burst",
                summary=(
                    f"{senders.distinct_senders} distinct senders in {BURST_WINDOW_HOURS} h "
                    f"into an account {age_days} days old, "
                    f"{flow_short.distinct_destinations} onward destination(s)."
                ),
                provenance=Provenance.INFERRED,
                source_entity_ids=[account_id, *senders.transaction_ids[:6]],
                points=POINTS["network.fan_in_burst"],
            )
        )
    elif not young and senders.distinct_senders >= FAN_IN_MIN_SENDERS:
        cleared.append(
            Evidence(
                id="network.established_account_cleared",
                summary=(
                    f"{senders.distinct_senders} senders in {BURST_WINDOW_HOURS} h, but the "
                    f"account is {age_days} days old; volume alone is not an indicator."
                ),
                provenance=Provenance.INFERRED,
                source_entity_ids=[account_id],
            )
        )

    if young and flow_short.velocity >= VELOCITY_MIN_TXNS:
        evidence.append(
            Evidence(
                id="network.high_velocity",
                summary=(
                    f"{flow_short.velocity} transactions in {BURST_WINDOW_HOURS} h on an account "
                    f"{age_days} days old."
                ),
                provenance=Provenance.INFERRED,
                source_entity_ids=[account_id],
                points=POINTS["network.high_velocity"],
            )
        )

    groups = {GROUPS[e.id] for e in evidence}
    if groups and age_days is not None and age_days <= 30:
        evidence.append(
            Evidence(
                id="network.account_age_context",
                summary=f"Account is {age_days} days old (supporting context only).",
                provenance=Provenance.INFERRED,
                source_entity_ids=[account_id],
                points=4 if age_days <= 14 else 2,
            )
        )

    for link in connections.neighbors:
        if link.rel_type != "CONNECTED_TO":
            continue
        cleared.append(
            Evidence(
                id="network.declared_connection",
                summary=(
                    f"Declared {link.kind or 'link'} between this account and another account."
                ),
                provenance=link.provenance or Provenance.VERIFIED_SYNTHETIC,
                source_entity_ids=[account_id, link.id],
            )
        )

    score = sum(e.points for e in evidence)
    if len(groups) < 2:
        score = min(score, SINGLE_GROUP_CAP)
    confidence = 0.5 + 0.1 * len(groups) if groups else 0.6
    return AgentFinding(
        agent_id="fraud_network",
        status="OK",
        score=min(100, score),
        confidence=round(min(confidence, 0.9), 2),
        evidence=[*evidence, *cleared],
    )


def unknown_recipient_finding() -> AgentFinding:
    return AgentFinding(agent_id="fraud_network", status="OK", score=0, confidence=0.2, evidence=[])


class FraudNetworkAgent(BaseAgent):
    """Custom ADK agent; every graph question is a recorded tool call."""

    recorder: Any
    graph: Any

    async def _run_async_impl(self, ctx: InvocationContext) -> AsyncGenerator[Event, None]:
        payment = PaymentContext.model_validate(ctx.session.state["payment"])
        recorder: ToolRecorder = self.recorder
        graph: GraphService = self.graph
        agent = "fraud_network"
        now: datetime = payment.now

        account_id = await recorder.call(
            agent,
            "account_for_owner",
            {"owner_id": payment.beneficiary_id},
            lambda: graph.account_for_owner(payment.beneficiary_id),
            _account_summary,
        )
        if account_id is None:
            finding = unknown_recipient_finding()
        else:
            age = await recorder.call(
                agent,
                "account_age_days",
                {"account_id": account_id, "as_of": now.isoformat()},
                lambda: graph.account_age_days(account_id, now),
                lambda d: f"{d} days",
            )
            senders = await recorder.call(
                agent,
                "recent_senders",
                {"account_id": account_id, "window_hours": BURST_WINDOW_HOURS},
                lambda: graph.recent_senders(account_id, BURST_WINDOW_HOURS, now),
                lambda s: f"{s.distinct_senders} senders, {s.transaction_count} transactions",
            )
            flow_long = await recorder.call(
                agent,
                "flow_profile",
                {"account_id": account_id, "window_hours": LONG_WINDOW_HOURS},
                lambda: graph.flow_profile(account_id, LONG_WINDOW_HOURS, now),
                _flow_summary,
            )
            flow_short = await recorder.call(
                agent,
                "flow_profile",
                {"account_id": account_id, "window_hours": BURST_WINDOW_HOURS},
                lambda: graph.flow_profile(account_id, BURST_WINDOW_HOURS, now),
                _flow_summary,
            )
            chains = await recorder.call(
                agent,
                "forwarding_chain",
                {
                    "account_id": account_id,
                    "window_hours": LONG_WINDOW_HOURS,
                    "max_hops": MAX_HOPS,
                    "max_gap_minutes": MAX_GAP_MINUTES,
                },
                lambda: graph.forwarding_chain(
                    account_id, LONG_WINDOW_HOURS, now, MAX_HOPS, MAX_GAP_MINUTES
                ),
                lambda c: f"{len(c.chains)} chains, max depth {c.max_depth}",
            )
            connections = await recorder.call(
                agent,
                "neighbors",
                {"id": account_id, "rel_types": ["CONNECTED_TO"]},
                lambda: graph.neighbors(account_id, ["CONNECTED_TO"]),
                lambda n: f"{len(n.neighbors)} declared connections",
            )
            finding = assess_network(
                beneficiary_id=payment.beneficiary_id,
                account_id=account_id,
                age_days=age,
                senders=senders,
                flow_long=flow_long,
                flow_short=flow_short,
                chains=chains,
                connections=connections,
            )
        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"finding": finding.model_dump(mode="json")}),
        )


def _account_summary(account_id: str | None) -> str:
    return account_id or "no account in graph"


def _flow_summary(f: FlowProfile) -> str:
    dwell = _minutes(f.median_dwell_minutes)
    retention = "n/a" if f.retention_ratio is None else f"{f.retention_ratio:.0%}"
    return (
        f"in {f.inbound_count}/{f.distinct_senders} senders, out {f.outbound_count}, "
        f"dwell {dwell}, retained {retention}, velocity {f.velocity}"
    )
