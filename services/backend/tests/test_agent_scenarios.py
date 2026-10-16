"""Detection outcomes must emerge from data and queries, with no per-recipient rules."""

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import pytest

from tests import support_graph
from tests.support_graph import NOW, GraphEnv
from tests.support_llm import scripted
from trustbank.agents import build_orchestrator
from trustbank.contracts import (
    Action,
    AgentFinding,
    Aggregate,
    DetectorResult,
    Level,
    PaymentContext,
    PolicyConfig,
)
from trustbank.domain import Provenance

graph_env = support_graph.graph_env

ELEVATED = 30

SCENARIOS = {
    "S1": ("cust_asha", "ben_rahul", 2500),
    "S2": ("cust_asha", "ben_sharma_store", 1200),
    "S3": ("cust_priya", "ben_sharma_store", 400),
    "S4": ("cust_priya", "ben_ananya", 600),
    "S5": ("cust_asha", "ben_greenleaf", 450),
    "S6": ("cust_asha", "ben_heritage", 40000),
    "S7": ("cust_asha", "ben_spice_garden", 1800),
    "S8": ("cust_asha", "ben_novatrade", 25000),
    "S9": ("cust_priya", "ben_novatrade", 8000),
    "S10": ("cust_asha", "ben_quickreturns", 5000),
}


class Sink:
    def __init__(self) -> None:
        self.events: list[tuple[str, str, dict[str, Any]]] = []

    def emit(self, agent_id: str, type: str, message: str, **kw: Any) -> None:
        self.events.append((agent_id, type, {"message": message, **kw}))


@dataclass
class Outcome:
    result: DetectorResult
    sink: Sink

    @property
    def pre(self) -> int:
        return round(0.4 * self.result.anomaly.score + 0.6 * self.result.fraud_network.score)

    @property
    def network_points(self) -> dict[str, int]:
        return {e.id: e.points for e in self.result.fraud_network.evidence if e.points > 0}

    def evidence_ids(self, finding: AgentFinding) -> set[str]:
        return {e.id for e in finding.evidence}


def run(env: GraphEnv, name: str, *, now: Any = NOW) -> Outcome:
    customer, beneficiary, amount = SCENARIOS[name]
    orchestrator = build_orchestrator(env.settings, env.graph, env.history, model=scripted())
    sink = Sink()
    ctx = PaymentContext(
        payment_id="p1", customer_id=customer, beneficiary_id=beneficiary, amount=amount, now=now
    )
    return Outcome(asyncio.run(orchestrator.run_detectors(ctx, sink)), sink)


@pytest.fixture(scope="module")
def outcomes(graph_env: GraphEnv) -> dict[str, Outcome]:
    graph_env.rebuild()
    return {name: run(graph_env, name) for name in SCENARIOS}


@pytest.mark.parametrize("name", ["S1", "S2", "S3", "S4", "S5", "S7"])
def test_benign_scenarios_stay_below_elevated(outcomes: dict[str, Outcome], name: str) -> None:
    o = outcomes[name]
    assert o.result.anomaly.status == o.result.fraud_network.status == "OK"
    assert o.pre < ELEVATED
    assert o.network_points == {}
    assert o.result.fraud_network.score == 0


def test_s2_shopkeeper_is_cleared_with_reasons(outcomes: dict[str, Outcome]) -> None:
    ids = outcomes["S2"].evidence_ids(outcomes["S2"].result.fraud_network)
    assert "network.long_dwell_cleared" in ids
    summary = next(
        e.summary
        for e in outcomes["S2"].result.fraud_network.evidence
        if e.id == "network.long_dwell_cleared"
    )
    assert "dwell" in summary and "retained" in summary and "single hop" in summary


@pytest.mark.parametrize("name", ["S3", "S4"])
def test_thin_payer_history_is_not_penalised(outcomes: dict[str, Outcome], name: str) -> None:
    anomaly = outcomes[name].result.anomaly
    assert "anomaly.limited_history" in outcomes[name].evidence_ids(anomaly)
    assert anomaly.confidence < 0.6
    assert anomaly.score < ELEVATED


def test_s5_young_account_alone_is_not_elevated(outcomes: dict[str, Outcome]) -> None:
    assert outcomes["S5"].pre < ELEVATED
    assert "network.account_age_context" not in outcomes["S5"].evidence_ids(
        outcomes["S5"].result.fraud_network
    )


def test_s6_anomaly_alone_elevates_without_network_evidence(
    outcomes: dict[str, Outcome],
) -> None:
    o = outcomes["S6"]
    assert o.result.anomaly.score >= 74
    assert o.result.fraud_network.score == 0 and o.network_points == {}
    assert ELEVATED <= o.pre < 60
    assert "anomaly.amount_deviation" in o.evidence_ids(o.result.anomaly)


def test_s7_pass_through_with_long_dwell_is_cleared(outcomes: dict[str, Outcome]) -> None:
    o = outcomes["S7"]
    ids = o.evidence_ids(o.result.fraud_network)
    assert {"network.long_dwell_cleared", "network.high_pass_through_cleared"} <= ids
    assert "network.declared_connection" in ids
    link = next(e for e in o.result.fraud_network.evidence if e.id == "network.declared_connection")
    assert link.provenance is Provenance.VERIFIED_SYNTHETIC and link.points == 0
    assert not o.network_points
    assert o.pre < ELEVATED


@pytest.mark.parametrize("name", ["S8", "S9"])
def test_novatrade_is_elevated_from_corroborated_behaviour(
    outcomes: dict[str, Outcome], name: str
) -> None:
    o = outcomes[name]
    assert {
        "network.rapid_pass_through",
        "network.multi_hop_layering",
        "network.fan_in_burst",
        "network.high_velocity",
    } <= set(o.network_points)
    assert all(
        e.provenance is Provenance.INFERRED for e in o.result.fraud_network.evidence if e.points
    )
    assert ELEVATED <= o.pre < 60


def test_s9_thin_history_gives_low_confidence_anomaly(outcomes: dict[str, Outcome]) -> None:
    assert outcomes["S9"].result.anomaly.confidence < 0.6
    assert outcomes["S9"].result.anomaly.score <= ELEVATED - 1
    assert outcomes["S9"].result.fraud_network.score == outcomes["S8"].result.fraud_network.score


def test_s8_summary_has_timings_and_no_names(outcomes: dict[str, Outcome]) -> None:
    network = outcomes["S8"].result.fraud_network
    layering = next(e for e in network.evidence if e.id == "network.multi_hop_layering")
    assert "hop 1" in layering.summary and "hop 3" in layering.summary
    rapid = next(e for e in network.evidence if e.id == "network.rapid_pass_through")
    assert "median dwell" in rapid.summary and "retained" in rapid.summary
    blob = json.dumps([e.summary for e in network.evidence]).lower()
    assert "nova" not in blob and "asha" not in blob


def test_s10_mid_chain_account_is_detected_from_its_own_behaviour(
    outcomes: dict[str, Outcome],
) -> None:
    o = outcomes["S10"]
    assert {"network.rapid_pass_through", "network.multi_hop_layering"} <= set(o.network_points)
    assert o.pre >= ELEVATED


def test_unknown_beneficiary_has_no_network_evidence(graph_env: GraphEnv) -> None:
    orchestrator = build_orchestrator(
        graph_env.settings, graph_env.graph, graph_env.history, model=scripted()
    )
    ctx = PaymentContext(
        payment_id="p", customer_id="cust_asha", beneficiary_id="ben_unknown", amount=500, now=NOW
    )
    result = asyncio.run(orchestrator.run_detectors(ctx, Sink()))
    assert result.fraud_network.status == "OK"
    assert result.fraud_network.score == 0 and result.fraud_network.evidence == []


def test_delaying_the_forwards_lowers_the_network_score(graph_env: GraphEnv) -> None:
    """Same accounts and amounts; only the timing of the onward transfers changes."""
    dataset = graph_env.dataset
    chain_accounts = {"acct_novatrade": 1, "acct_quickreturns": 2, "acct_taskrewards": 3}
    delay = timedelta(days=1)
    shifted = tuple(
        t.model_copy(
            update={"timestamp": t.timestamp + delay * chain_accounts[t.source_account_id]}
        )
        if t.source_account_id in chain_accounts
        else t
        for t in dataset.transactions
    )
    later = NOW + timedelta(days=3)
    try:
        baseline = run(graph_env, "S8", now=later)
        graph_env.rebuild(dataset.model_copy(update={"transactions": shifted}))
        delayed = run(graph_env, "S8", now=later)
    finally:
        graph_env.rebuild()
    assert "network.rapid_pass_through" in baseline.network_points
    assert "network.multi_hop_layering" in baseline.network_points
    assert delayed.result.fraud_network.score < baseline.result.fraud_network.score
    assert "network.rapid_pass_through" not in delayed.network_points
    assert "network.multi_hop_layering" not in delayed.network_points
    assert delayed.pre < ELEVATED + 20


def test_detector_timeline_and_tool_calls(outcomes: dict[str, Outcome]) -> None:
    o = outcomes["S8"]
    kinds = {(a, t) for a, t, _ in o.sink.events}
    assert {
        ("anomaly", "STARTED"),
        ("fraud_network", "STARTED"),
        ("anomaly", "FINDING"),
        ("fraud_network", "COMPLETED"),
        ("fraud_network", "TOOL_CALL"),
        ("orchestrator", "COMPLETED"),
    } <= kinds
    tools = {c.tool for c in o.result.tool_calls if c.agent_id == "fraud_network"}
    assert {"flow_profile", "forwarding_chain", "recent_senders", "account_age_days"} <= tools
    assert all(c.duration_ms >= 0 and c.result_summary for c in o.result.tool_calls)


_SCENARIO_WORDS = re.compile(
    r"\bS(?:10|[1-9])\b|scenario|expected|false.positive|\bmule\b|shopkeeper|genuine|benign",
    re.I,
)


def test_agents_are_scenario_blind(outcomes: dict[str, Outcome], graph_env: GraphEnv) -> None:
    for name, o in outcomes.items():
        for call in o.result.tool_calls:
            assert not _SCENARIO_WORDS.search(json.dumps(call.parameters)), (name, call)
        for _, _, payload in o.sink.events:
            assert not _SCENARIO_WORDS.search(json.dumps(payload, default=str)), (name, payload)

    llm = scripted(
        '{"questions":[{"id":"source_of_details","text":"How did you get the details?",'
        '"signal_ids":["network.rapid_pass_through"]},{"id":"promised_benefit","text":"Were you '
        'promised anything?","signal_ids":["network.rapid_pass_through"]},{"id":'
        '"urgency_or_secrecy","text":"Is anyone rushing you?","signal_ids":'
        '["network.rapid_pass_through"]}]}',
        '{"text":"Money sent here appears to be moved on within minutes.",'
        '"cited_evidence_ids":["network.rapid_pass_through"]}',
    )
    orchestrator = build_orchestrator(
        graph_env.settings, graph_env.graph, graph_env.history, model=llm
    )
    detectors = outcomes["S8"].result
    findings = [detectors.anomaly, detectors.fraud_network]
    ctx = PaymentContext(
        payment_id="p",
        customer_id="cust_asha",
        beneficiary_id="ben_novatrade",
        amount=25000,
        now=NOW,
    )
    sink = Sink()
    asyncio.run(orchestrator.ask_questions(ctx, findings, sink))
    aggregate = Aggregate(
        anomaly_score=69, network_score=50, pre_score=58, context_points=0, final_score=58,
        level=Level.MEDIUM, action=Action.REVIEW, elevated=True, incomplete=False,
        evidence_cap_applied=False,
    )  # fmt: skip
    asyncio.run(orchestrator.explain(ctx, findings, aggregate, sink))
    assert len(llm.prompts) == 2
    for text in [*llm.prompts, *llm.instructions]:
        assert not _SCENARIO_WORDS.search(text), text
        assert "nova" not in text.lower() and "asha" not in text.lower()
    assert PolicyConfig().elevated_threshold == ELEVATED
