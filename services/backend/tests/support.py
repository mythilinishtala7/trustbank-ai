"""Test doubles: deterministic orchestrator and graph, fixed clock."""

import asyncio
import threading
from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from trustbank.contracts import (
    AgentFinding,
    Aggregate,
    Answer,
    AnswerResult,
    DetectorResult,
    Evidence,
    Explanation,
    Option,
    PaymentContext,
    PolicyConfig,
    Question,
    QuestionnaireResult,
    ToolCall,
    TraceSink,
)
from trustbank.domain import Provenance, Transaction
from trustbank.graph.views import GraphEdge, GraphNode, GraphView

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


def _network_evidence() -> list[Evidence]:
    return [
        Evidence(
            id="network.fan_in",
            summary="Many senders paid this account within hours.",
            provenance=Provenance.INFERRED,
            source_entity_ids=["acct_novatrade", "txn_net_in_1"],
            points=30,
        ),
        Evidence(
            id="network.layering",
            summary="Funds were forwarded within minutes.",
            provenance=Provenance.INFERRED,
            source_entity_ids=["acct_quickreturns"],
            points=40,
        ),
    ]


QUESTIONS = [
    Question(
        id="source_of_details",
        text="How did you get these payment details?",
        signal_ids=["network.fan_in"],
        options=[
            Option(value="friend_family", label="A friend or family member"),
            Option(value="messaging_app", label="A messaging app"),
        ],
        allow_free_text=True,
    ),
    Question(
        id="promised_benefit",
        text="Were you promised a return?",
        signal_ids=["network.layering"],
        options=[Option(value="yes", label="Yes"), Option(value="no", label="No")],
    ),
]


class StubOrchestrator:
    """Scripted by beneficiary id. Emits trace events like the real agents."""

    model_name = "stub-model"

    def __init__(self) -> None:
        self.detector_calls: list[str] = []
        self.gate: threading.Event | None = None
        self.explanation_text = "Please check this payment carefully."
        self.explain_raises = False
        self.detectors_raise_for: set[str] = set()
        self.failed_detector_for: set[str] = set()

    async def run_detectors(self, ctx: PaymentContext, trace: TraceSink) -> DetectorResult:
        self.detector_calls.append(ctx.payment_id)
        trace.emit("anomaly", "STARTED", "Anomaly detector started")
        trace.emit("fraud_network", "STARTED", "Network detector started")
        while self.gate is not None and not self.gate.is_set():
            await asyncio.sleep(0.02)
        if ctx.beneficiary_id in self.detectors_raise_for:
            raise RuntimeError("detector exploded: secret-internal-detail")
        anomaly_score, network_score, evidence = 0, 0, []
        if ctx.beneficiary_id == "ben_novatrade":
            anomaly_score, network_score, evidence = 40, 70, _network_evidence()
        elif ctx.beneficiary_id == "ben_heritage":
            anomaly_score = 75  # elevated by anomaly alone: no network evidence
        status = "FAILED" if ctx.beneficiary_id in self.failed_detector_for else "OK"
        trace.emit("fraud_network", "FINDING", "Network finding", status=status)
        started = ctx.now
        return DetectorResult(
            anomaly=AgentFinding(
                agent_id="anomaly", status="OK", score=anomaly_score, confidence=0.9
            ),
            fraud_network=AgentFinding(
                agent_id="fraud_network",
                status=status,
                score=0 if status == "FAILED" else network_score,
                confidence=0.8,
                evidence=evidence,
                error="graph down" if status == "FAILED" else None,
            ),
            tool_calls=[
                ToolCall(
                    agent_id="fraud_network",
                    tool="flow_profile",
                    parameters={"account": "acct_x"},
                    result_summary="ok",
                    started_at=started,
                    duration_ms=3,
                )
            ],
        )

    async def ask_questions(
        self, ctx: PaymentContext, findings: list[AgentFinding], trace: TraceSink
    ) -> QuestionnaireResult:
        trace.emit("questionnaire", "COMPLETED", "Questions prepared", status="OK")
        return QuestionnaireResult(questions=QUESTIONS)

    async def interpret_answers(
        self,
        ctx: PaymentContext,
        questions: list[Question],
        answers: list[Answer],
        findings: list[AgentFinding],
        config: PolicyConfig,
        trace: TraceSink,
    ) -> AnswerResult:
        chosen = {a.question_id: a.option for a in answers}
        scam = (
            chosen.get("source_of_details") == "messaging_app"
            and chosen.get("promised_benefit") == "yes"
        )
        points = 25 if scam else 0
        trace.emit("questionnaire", "FINDING", "Answers interpreted", status="OK")
        return AnswerResult(
            finding=AgentFinding(
                agent_id="questionnaire",
                status="OK",
                score=points,
                confidence=0.9,
                evidence=[
                    Evidence(
                        id="context.scam_pattern",
                        summary="Answers match a known scam pattern.",
                        provenance=Provenance.USER_PROVIDED,
                        points=points,
                    )
                ]
                if points
                else [],
            )
        )

    async def explain(
        self,
        ctx: PaymentContext,
        findings: list[AgentFinding],
        aggregate: Aggregate,
        trace: TraceSink,
    ) -> Explanation:
        trace.emit("explainer", "COMPLETED", "Explanation written", status="OK")
        if self.explain_raises:
            raise RuntimeError("model unavailable")
        return Explanation(
            text=self.explanation_text,
            reasons=["The recipient account is new to you", "Check with them another way"],
            evidence_ids=["network.fan_in"],
            status="OK",
        )


class StubGraph:
    def __init__(self) -> None:
        self.projected: list[Transaction] = []
        self.signals: list[tuple[str, str, list[Evidence]]] = []
        self.graph_calls: list[dict[str, object]] = []
        self.fail_projection = False
        self.up = True

    def ping(self) -> bool:
        if not self.up:
            raise ConnectionError("neo4j down")
        return True

    def project_transaction(self, txn: Transaction) -> None:
        if self.fail_projection:
            raise ConnectionError("neo4j down")
        self.projected.append(txn)

    def record_signals(
        self, transaction_id: str, beneficiary_id: str, evidence: list[Evidence]
    ) -> None:
        self.signals.append((transaction_id, beneficiary_id, evidence))

    def investigation_graph(
        self,
        *,
        customer_id: str,
        beneficiary_id: str,
        transaction_id: str | None,
        highlight_ids: Collection[str],
        max_nodes: int = 80,
    ) -> GraphView:
        self.graph_calls.append(
            {
                "customer_id": customer_id,
                "beneficiary_id": beneficiary_id,
                "transaction_id": transaction_id,
                "highlight_ids": set(highlight_ids),
            }
        )
        return GraphView(
            nodes=[
                GraphNode(
                    id=beneficiary_id,
                    label="Beneficiary",
                    name="Recipient",
                    highlighted=beneficiary_id in highlight_ids,
                )
            ],
            edges=[GraphEdge(id="e1", source=customer_id, target=beneficiary_id, type="PAID")],
        )
