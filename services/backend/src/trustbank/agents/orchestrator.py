"""ADK-backed orchestrator implementing `contracts.Orchestrator`.

It runs the two detectors in parallel under per-agent timeouts, drives the questionnaire and
explainer, and reports every step to the timeline. It returns evidence and recommendations only:
it never changes payment state.
"""

import asyncio
import time
import uuid
from typing import Literal

from google.adk.agents import BaseAgent
from google.adk.models import BaseLlm
from google.adk.runners import InMemoryRunner
from google.genai import types

from trustbank.agents import explainer, questionnaire
from trustbank.agents.anomaly import AnomalyAgent, HistoryReader
from trustbank.agents.network import FraudNetworkAgent
from trustbank.agents.recorder import ToolRecorder
from trustbank.contracts import (
    AgentFinding,
    Aggregate,
    Answer,
    AnswerResult,
    DetectorResult,
    Explanation,
    PaymentContext,
    PolicyConfig,
    Question,
    QuestionnaireResult,
    TraceSink,
)
from trustbank.graph import GraphService

DETECTOR_TIMEOUT_SECONDS = 8.0
LLM_TIMEOUT_SECONDS = 15.0

DetectorId = Literal["anomaly", "fraud_network"]


def _describe(exc: BaseException) -> str:
    detail = str(exc).strip().splitlines()[0][:160] if str(exc).strip() else ""
    return f"{type(exc).__name__}: {detail}" if detail else type(exc).__name__


class AdkOrchestrator:
    def __init__(
        self,
        *,
        model: BaseLlm,
        graph: GraphService,
        history: HistoryReader,
        detector_timeout: float = DETECTOR_TIMEOUT_SECONDS,
        llm_timeout: float = LLM_TIMEOUT_SECONDS,
    ) -> None:
        self._model = model
        self._graph = graph
        self._history = history
        self._detector_timeout = detector_timeout
        self._llm_timeout = llm_timeout
        self.model_name: str = model.model

    async def run_detectors(self, ctx: PaymentContext, trace: TraceSink) -> DetectorResult:
        recorder = ToolRecorder(trace)
        trace.emit(
            "orchestrator", "STARTED", "Running anomaly and fraud-network detectors in parallel"
        )
        anomaly, network = await asyncio.gather(
            self._run_detector(
                "anomaly",
                AnomalyAgent(name="anomaly", recorder=recorder, history=self._history),
                ctx,
                trace,
            ),
            self._run_detector(
                "fraud_network",
                FraudNetworkAgent(name="fraud_network", recorder=recorder, graph=self._graph),
                ctx,
                trace,
            ),
        )
        failed = [f.agent_id for f in (anomaly, network) if f.status != "OK"]
        trace.emit(
            "orchestrator",
            "FAILED" if failed else "COMPLETED",
            f"Detectors incomplete: {', '.join(failed)}" if failed else "Detectors finished",
            status="INCOMPLETE" if failed else "OK",
        )
        return DetectorResult(anomaly=anomaly, fraud_network=network, tool_calls=recorder.calls)

    async def ask_questions(
        self, ctx: PaymentContext, findings: list[AgentFinding], trace: TraceSink
    ) -> QuestionnaireResult:
        trace.emit("questionnaire", "STARTED", "Preparing questions for the customer")
        started = time.perf_counter()
        try:
            questions = await questionnaire.draft_questions(
                self._model, findings, self._llm_timeout
            )
        except Exception as exc:
            questions = questionnaire.fixed_questions(findings)
            trace.emit(
                "questionnaire",
                "FALLBACK",
                "Model output unusable; using fixed allow-listed questions",
                status="DEGRADED",
                result_summary=_describe(exc),
            )
            degraded = True
        else:
            degraded = False
        trace.emit(
            "questionnaire",
            "COMPLETED",
            f"{len(questions)} questions ready",
            status="DEGRADED" if degraded else "OK",
            duration_ms=_ms(started),
        )
        return QuestionnaireResult(questions=questions, degraded=degraded)

    async def interpret_answers(
        self,
        ctx: PaymentContext,
        questions: list[Question],
        answers: list[Answer],
        findings: list[AgentFinding],
        config: PolicyConfig,
        trace: TraceSink,
    ) -> AnswerResult:
        trace.emit("questionnaire", "STARTED", "Interpreting the customer's answers")
        started = time.perf_counter()
        mapped = questionnaire.map_answers(questions, answers)
        evidence = list(mapped.evidence)
        degraded = mapped.dropped > 0
        asked = {q.id for q in questions if q.allow_free_text}
        notes = [
            a.free_text.strip()
            for a in answers
            if a.free_text and a.free_text.strip() and a.question_id in asked
        ]
        if notes:
            try:
                verdict = await questionnaire.classify_free_text(
                    self._model, " ".join(notes)[:300], self._llm_timeout
                )
                evidence.append(questionnaire.free_text_evidence(verdict, config))
            except Exception as exc:
                degraded = True
                trace.emit(
                    "questionnaire",
                    "FALLBACK",
                    "Free-text classification unavailable; note contributes no points",
                    status="DEGRADED",
                    result_summary=_describe(exc),
                )
        total = min(100, sum(e.points for e in evidence))
        finding = AgentFinding(
            agent_id="questionnaire",
            status="DEGRADED" if degraded else "OK",
            score=total,
            confidence=0.8 if evidence else 0.3,
            evidence=evidence,
        )
        trace.emit(
            "questionnaire",
            "FINDING",
            f"Answers added {total} context points",
            status=finding.status,
            result_summary=", ".join(f"{e.id}={e.points}" for e in evidence),
        )
        trace.emit(
            "questionnaire",
            "COMPLETED",
            "Answers interpreted",
            status=finding.status,
            duration_ms=_ms(started),
        )
        return AnswerResult(finding=finding)

    async def explain(
        self,
        ctx: PaymentContext,
        findings: list[AgentFinding],
        aggregate: Aggregate,
        trace: TraceSink,
    ) -> Explanation:
        trace.emit("explainer", "STARTED", "Writing the customer explanation")
        started = time.perf_counter()
        try:
            result = await explainer.explain(self._model, findings, aggregate, self._llm_timeout)
        except Exception as exc:
            facts = explainer.customer_facts(findings)
            result = explainer.template_explanation(aggregate.action, facts, degraded=True)
            trace.emit(
                "explainer",
                "FALLBACK",
                "Model explanation rejected; using the template explanation",
                status="DEGRADED",
                result_summary=_describe(exc),
            )
        trace.emit(
            "explainer",
            "COMPLETED",
            "Explanation ready",
            status=result.status,
            duration_ms=_ms(started),
        )
        return result

    async def _run_detector(
        self, agent_id: DetectorId, agent: BaseAgent, ctx: PaymentContext, trace: TraceSink
    ) -> AgentFinding:
        started = time.perf_counter()
        trace.emit(agent_id, "STARTED", f"{agent_id} detector started")
        try:
            finding = await asyncio.wait_for(
                _run_state_agent(agent, ctx), timeout=self._detector_timeout
            )
        except TimeoutError:
            finding = _failed(agent_id, "TIMEOUT", f"no result within {self._detector_timeout:g}s")
        except Exception as exc:
            finding = _failed(agent_id, "FAILED", _describe(exc))
        duration = _ms(started)
        if finding.status == "OK":
            trace.emit(
                agent_id,
                "FINDING",
                f"score {finding.score}, {len(finding.evidence)} evidence items",
                status="OK",
                result_summary=", ".join(f"{e.id}={e.points}" for e in finding.evidence),
            )
            trace.emit(
                agent_id, "COMPLETED", "Detector completed", status="OK", duration_ms=duration
            )
        else:
            trace.emit(
                agent_id,
                "FAILED",
                f"Detector {finding.status.lower()}",
                status=finding.status,
                duration_ms=duration,
                result_summary=finding.error,
            )
        return finding


def _failed(agent_id: DetectorId, status: Literal["FAILED", "TIMEOUT"], error: str) -> AgentFinding:
    return AgentFinding(agent_id=agent_id, status=status, score=0, confidence=0.0, error=error)


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


async def _run_state_agent(agent: BaseAgent, ctx: PaymentContext) -> AgentFinding:
    app = "agents"
    runner = InMemoryRunner(agent=agent, app_name=app)
    session = await runner.session_service.create_session(
        app_name=app,
        user_id="system",
        session_id=uuid.uuid4().hex,
        state={"payment": ctx.model_dump(mode="json")},
    )
    async for _ in runner.run_async(
        user_id="system",
        session_id=session.id,
        new_message=types.Content(role="user", parts=[types.Part(text="assess")]),
    ):
        pass
    final = await runner.session_service.get_session(
        app_name=app, user_id="system", session_id=session.id
    )
    payload = final.state.get("finding") if final else None
    if payload is None:
        raise RuntimeError("detector produced no finding")
    return AgentFinding.model_validate(payload)
