import pytest

from trustbank.contracts import Action, AgentFinding, Evidence, Level, PolicyConfig
from trustbank.domain import Provenance
from trustbank.policy import aggregate

CONFIG = PolicyConfig()


def finding(
    agent: str, score: int, *, status: str = "OK", evidence: list[Evidence] | None = None
) -> AgentFinding:
    return AgentFinding(
        agent_id=agent,
        status=status,
        score=score,
        confidence=0.9,
        evidence=evidence or [],
    )


def net_evidence(points: int = 10) -> list[Evidence]:
    return [
        Evidence(id="network.fan_in", summary="s", provenance=Provenance.INFERRED, points=points)
    ]


def context(points: int, evidence_id: str = "context.scam_pattern") -> AgentFinding:
    return finding(
        "questionnaire",
        points,
        evidence=[
            Evidence(
                id=evidence_id, summary="s", provenance=Provenance.USER_PROVIDED, points=points
            )
        ],
    )


@pytest.mark.parametrize(
    ("anomaly", "network", "pre", "level", "action"),
    [
        (0, 0, 0, Level.LOW, Action.PROCEED),
        (40, 40, 40, Level.MEDIUM, Action.REVIEW),
        (20, 30, 26, Level.LOW, Action.PROCEED),
        (30, 30, 30, Level.MEDIUM, Action.REVIEW),
        (50, 70, 62, Level.HIGH, Action.HOLD),
        (100, 100, 100, Level.HIGH, Action.HOLD),
        (10, 83, 54, Level.MEDIUM, Action.REVIEW),
    ],
)
def test_levels_and_actions(
    anomaly: int, network: int, pre: int, level: Level, action: Action
) -> None:
    result = aggregate(
        finding("anomaly", anomaly),
        finding("fraud_network", network, evidence=net_evidence()),
        None,
        CONFIG,
    )
    assert (result.pre_score, result.level, result.action) == (pre, level, action)
    assert result.elevated == (pre >= 30)
    assert not result.incomplete and not result.evidence_cap_applied


def test_pre_score_is_weighted_and_rounded() -> None:
    result = aggregate(finding("anomaly", 55), finding("fraud_network", 33), None, CONFIG)
    assert result.pre_score == round(0.4 * 55 + 0.6 * 33)  # 41.8 -> 42


def test_context_points_added_and_clamped() -> None:
    base = aggregate(
        finding("anomaly", 40), finding("fraud_network", 40, evidence=net_evidence()), None, CONFIG
    )
    final = aggregate(
        finding("anomaly", 40),
        finding("fraud_network", 40, evidence=net_evidence()),
        context(25),
        CONFIG,
    )
    assert final.context_points == 25 and final.final_score == base.pre_score + 25
    assert final.action is Action.HOLD
    maxed = aggregate(
        finding("anomaly", 100),
        finding("fraud_network", 100, evidence=net_evidence()),
        context(50),
        CONFIG,
    )
    assert maxed.final_score == 100


def test_not_high_on_anomaly_alone() -> None:
    result = aggregate(finding("anomaly", 100), finding("fraud_network", 0), None, CONFIG)
    assert result.pre_score == 40
    assert result.level is not Level.HIGH
    assert result.action is Action.REVIEW


def test_evidence_cap_applies_without_network_evidence() -> None:
    # 100 anomaly + 100 network score but no network evidence points: capped at 59.
    result = aggregate(finding("anomaly", 100), finding("fraud_network", 100), None, CONFIG)
    assert result.final_score == 59 and result.evidence_cap_applied
    assert result.action is Action.REVIEW


def test_evidence_cap_lifted_by_network_evidence() -> None:
    result = aggregate(
        finding("anomaly", 100),
        finding("fraud_network", 100, evidence=net_evidence()),
        None,
        CONFIG,
    )
    assert result.final_score == 100 and not result.evidence_cap_applied
    assert result.action is Action.HOLD


def test_context_evidence_with_zero_points_does_not_lift_cap() -> None:
    zero = [Evidence(id="network.cleared", summary="s", provenance=Provenance.INFERRED, points=0)]
    result = aggregate(
        finding("anomaly", 100), finding("fraud_network", 100, evidence=zero), None, CONFIG
    )
    assert result.evidence_cap_applied and result.final_score == 59


def test_evidence_cap_lifted_when_context_alone_reaches_40() -> None:
    result = aggregate(finding("anomaly", 60), finding("fraud_network", 0), context(40), CONFIG)
    assert result.final_score == 64 and not result.evidence_cap_applied
    assert result.action is Action.HOLD
    below = aggregate(finding("anomaly", 60), finding("fraud_network", 0), context(39), CONFIG)
    assert below.final_score == 59 and below.evidence_cap_applied


def test_free_text_points_are_capped() -> None:
    result = aggregate(
        finding("anomaly", 0),
        finding("fraud_network", 50, evidence=net_evidence()),
        context(25, evidence_id="context.free_text_scam_script"),
        CONFIG,
    )
    assert result.context_points == CONFIG.context_cap


@pytest.mark.parametrize("status", ["FAILED", "TIMEOUT"])
@pytest.mark.parametrize("which", ["anomaly", "fraud_network"])
def test_incomplete_never_low(status: str, which: str) -> None:
    anomaly = finding("anomaly", 0, status=status if which == "anomaly" else "OK")
    network = finding("fraud_network", 0, status=status if which == "fraud_network" else "OK")
    result = aggregate(anomaly, network, None, CONFIG)
    assert result.incomplete
    assert result.level is Level.MEDIUM and result.action is Action.REVIEW
    assert not result.elevated


def test_incomplete_does_not_lower_a_hold() -> None:
    result = aggregate(
        finding("anomaly", 100, status="TIMEOUT"),
        finding("fraud_network", 100, evidence=net_evidence()),
        None,
        CONFIG,
    )
    assert result.incomplete and result.action is Action.HOLD


def test_degraded_detector_is_not_incomplete() -> None:
    result = aggregate(
        finding("anomaly", 0, status="DEGRADED"), finding("fraud_network", 0), None, CONFIG
    )
    assert not result.incomplete and result.action is Action.PROCEED


def test_reproducible() -> None:
    args = (
        finding("anomaly", 41),
        finding("fraud_network", 67, evidence=net_evidence()),
        context(17),
        CONFIG,
    )
    assert aggregate(*args) == aggregate(*args)
    assert aggregate(*args).model_dump() == aggregate(*args).model_dump()


def test_custom_config_is_honoured() -> None:
    strict = PolicyConfig(elevated_threshold=10, high_threshold=40)
    result = aggregate(
        finding("anomaly", 30), finding("fraud_network", 40, evidence=net_evidence()), None, strict
    )
    assert result.pre_score == 36 and result.elevated and result.level is Level.MEDIUM
