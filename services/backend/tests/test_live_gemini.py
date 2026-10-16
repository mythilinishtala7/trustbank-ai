"""Live Gemini smoke test. Excluded by default; run with `pytest -m live`."""

import asyncio
import os
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from trustbank.agents import build_orchestrator
from trustbank.config import Settings
from trustbank.contracts import (
    Action,
    AgentFinding,
    Aggregate,
    Evidence,
    Level,
    PaymentContext,
)
from trustbank.domain import Provenance
from trustbank.graph import GraphService
from trustbank.store import DatasetRepository

pytestmark = pytest.mark.live


class Sink:
    def emit(self, *args: Any, **kwargs: Any) -> None:
        pass


def test_gemini_writes_questions_and_an_explanation() -> None:
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    settings = Settings(_env_file=None, environment="test")
    orch = build_orchestrator(settings, cast(GraphService, None), cast(DatasetRepository, None))
    ctx = PaymentContext(
        payment_id="p", customer_id="c", beneficiary_id="b", amount=100,
        now=datetime.now(UTC),
    )  # fmt: skip
    findings = [
        AgentFinding(
            agent_id="fraud_network",
            status="OK",
            score=42,
            confidence=0.8,
            evidence=[
                Evidence(
                    id="network.rapid_pass_through",
                    summary="s",
                    provenance=Provenance.INFERRED,
                    points=20,
                )
            ],
        )  # fmt: skip
    ]
    questions = asyncio.run(orch.ask_questions(ctx, findings, Sink()))
    assert len(questions.questions) == 3
    aggregate = Aggregate(
        anomaly_score=30, network_score=42, pre_score=37, context_points=0, final_score=37,
        level=Level.MEDIUM, action=Action.REVIEW, elevated=True, incomplete=False,
        evidence_cap_applied=False,
    )  # fmt: skip
    explanation = asyncio.run(orch.explain(ctx, findings, aggregate, Sink()))
    assert explanation.status == "OK", explanation
    assert not questions.degraded
