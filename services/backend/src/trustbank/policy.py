"""Deterministic risk policy. Pure functions: identical inputs give identical results.

Agents supply findings; only this module maps them to a level and an action.
"""

from decimal import ROUND_HALF_UP, Decimal

from trustbank.config import Settings
from trustbank.contracts import Action, AgentFinding, Aggregate, Level, PolicyConfig
from trustbank.domain import Provenance

FAILED_STATUSES = frozenset({"FAILED", "TIMEOUT"})


def policy_config_from(settings: Settings) -> PolicyConfig:
    return PolicyConfig(
        anomaly_weight=settings.anomaly_weight,
        network_weight=settings.network_weight,
        elevated_threshold=settings.elevated_threshold,
        high_threshold=settings.high_threshold,
        hold_seconds=settings.hold_seconds,
    )


def _round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _clamp(value: int, low: int = 0, high: int = 100) -> int:
    return max(low, min(high, value))


def _context_points(finding: AgentFinding | None, config: PolicyConfig) -> int:
    """Sum of USER_PROVIDED evidence points; free-text classification is capped separately."""
    if finding is None:
        return 0
    structured = 0
    free_text = 0
    for item in finding.evidence:
        if item.provenance is not Provenance.USER_PROVIDED:
            continue
        if "free_text" in item.id:
            free_text += item.points
        else:
            structured += item.points
    return structured + min(free_text, config.context_cap)


def has_network_evidence(network: AgentFinding) -> bool:
    return any(item.points > 0 for item in network.evidence)


def aggregate(
    anomaly: AgentFinding,
    network: AgentFinding,
    questionnaire: AgentFinding | None,
    config: PolicyConfig,
) -> Aggregate:
    """Aggregate detector findings (and, once answered, the questionnaire finding)."""
    pre = _round_half_up(
        Decimal(str(config.anomaly_weight)) * anomaly.score
        + Decimal(str(config.network_weight)) * network.score
    )
    context = _context_points(questionnaire, config)
    final = _clamp(pre + context)

    capped = False
    if not has_network_evidence(network) and context < config.evidence_cap_context:
        if final > config.evidence_cap_score:
            final = config.evidence_cap_score
            capped = True

    if final >= config.high_threshold:
        level, action = Level.HIGH, Action.HOLD
    elif final >= config.elevated_threshold:
        level, action = Level.MEDIUM, Action.REVIEW
    else:
        level, action = Level.LOW, Action.PROCEED

    incomplete = any(f.status in FAILED_STATUSES for f in (anomaly, network))
    if incomplete and action is Action.PROCEED:
        # A failed detector never lowers risk: missing evidence resolves to at least REVIEW.
        level, action = Level.MEDIUM, Action.REVIEW

    return Aggregate(
        anomaly_score=anomaly.score,
        network_score=network.score,
        pre_score=pre,
        context_points=context,
        final_score=final,
        level=level,
        action=action,
        elevated=pre >= config.elevated_threshold,
        incomplete=incomplete,
        evidence_cap_applied=capped,
    )
