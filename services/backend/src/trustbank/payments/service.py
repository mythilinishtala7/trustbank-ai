"""Payment service: the only component that changes payment state (agents only advise)."""

import asyncio
import logging
import re
import time
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from zlib import crc32

from trustbank.contracts import (
    Action,
    AgentFinding,
    Aggregate,
    Answer,
    Evidence,
    Explanation,
    Orchestrator,
    PaymentContext,
    PaymentStatus,
    PolicyConfig,
    Question,
    ToolCall,
    TraceSink,
)
from trustbank.domain import (
    Account,
    Beneficiary,
    OwnerType,
    Provenance,
    Transaction,
)
from trustbank.errors import (
    ApiError,
    hold_active,
    invalid_transition,
    not_found,
    validation_error,
)
from trustbank.fixtures import account_id
from trustbank.graph import GraphService
from trustbank.payments.models import Assessment, PaymentDoc
from trustbank.payments.repo import (
    PaymentRepository,
    TxnContext,
    idempotency_id,
    new_assessment_id,
    new_payment_id,
)
from trustbank.payments.state import Event, InvalidTransitionError, next_status
from trustbank.payments.trace import TraceHub
from trustbank.policy import aggregate
from trustbank.recipients import UNVERIFIED_PREFIX, resolve
from trustbank.store import (
    ACCOUNTS,
    BENEFICIARIES,
    CUSTOMERS,
    TRANSACTIONS,
    DatasetRepository,
)

log = logging.getLogger("trustbank.payments")

PIN_FORMAT = re.compile(r"^\d{4,6}$")
S = PaymentStatus

_FALLBACK_EXPLANATION = Explanation(
    text=(
        "We could not complete every safety check on this payment. "
        "Please review the details carefully before you continue."
    ),
    reasons=["Some of our checks were unavailable"],
    evidence_ids=[],
    status="DEGRADED",
)


def _failed(agent_id: str) -> AgentFinding:
    return AgentFinding(
        agent_id=agent_id,
        status="FAILED",
        score=0,
        confidence=0.0,
        error="Detector unavailable",
    )


def _ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


class PaymentService:
    def __init__(
        self,
        *,
        orchestrator: Orchestrator,
        graph: GraphService,
        dataset: DatasetRepository,
        payments: PaymentRepository,
        hub: TraceHub,
        config: PolicyConfig,
        clock: Callable[[], datetime],
    ) -> None:
        self._orch = orchestrator
        self._graph = graph
        self._dataset = dataset
        self._repo = payments
        self._hub = hub
        self._config = config
        self._clock = clock

    @property
    def config(self) -> PolicyConfig:
        return self._config

    # ------------------------------------------------------------------ helpers

    @contextmanager
    def _operation(self, payment_id: str) -> Iterator[TraceSink]:
        """While open, SSE streams know more trace events may still arrive for this payment."""
        self._hub.begin_operation(payment_id)
        try:
            yield self._hub.sink(payment_id)
        finally:
            self._hub.end_operation(payment_id)

    def _load(self, payment_id: str, customer_id: str | None = None) -> PaymentDoc:
        doc = self._repo.get(payment_id)
        if doc is None or (customer_id is not None and doc.customer_id != customer_id):
            raise not_found("Payment not found.")
        return doc

    def _audit(self, action: str, doc_or_id: str, actor: str) -> None:
        try:
            self._repo.audit(self._clock(), action, actor, payment_id=doc_or_id)
        except Exception as exc:  # audit must not break the customer flow
            log.error("audit_failed", extra={"action": action, "error_type": type(exc).__name__})

    def _transition(
        self,
        payment_id: str,
        event: Event,
        sink: TraceSink,
        *,
        customize: Callable[[PaymentDoc, datetime], PaymentDoc] | None = None,
        reason: str = "",
        actor: str = "system",
        guard: Callable[[PaymentDoc], ApiError | None] | None = None,
    ) -> PaymentDoc:
        now = self._clock()

        def apply(ctx: TxnContext) -> tuple[PaymentStatus, PaymentDoc]:
            doc = ctx.payment
            if doc is None:
                raise not_found("Payment not found.")
            if guard and (error := guard(doc)):
                raise error
            try:
                target = next_status(doc.status, event)
            except InvalidTransitionError:
                raise invalid_transition(
                    f"This payment is {doc.status.value.lower().replace('_', ' ')} "
                    "and cannot take that action."
                ) from None
            updated = doc.model_copy(update={"status": target, "updated_at": now})
            if customize:
                updated = customize(updated, now)
            ctx.put_payment(updated)
            return doc.status, updated

        previous, updated = self._repo.transact(payment_id, apply)
        suffix = f": {reason}" if reason else ""
        sink.emit(
            "orchestrator",
            "STATE_CHANGE",
            f"Payment {previous.value} -> {updated.status.value}{suffix}",
            status=updated.status.value,
        )
        self._audit(f"PAYMENT_{event.value}", payment_id, actor)
        log.info(
            "payment_transition",
            extra={
                "payment_id": payment_id,
                "from_status": previous.value,
                "to_status": updated.status.value,
            },
        )
        return updated

    def _refresh(self, payment_id: str, customer_id: str | None = None) -> PaymentDoc:
        """Evaluate hold expiry by server time (on every read and action). Never auto-releases."""
        doc = self._load(payment_id, customer_id)
        now = self._clock()
        if not (doc.status is S.HOLD_ACTIVE and doc.hold_until and now >= doc.hold_until):
            return doc

        def apply(ctx: TxnContext) -> bool:
            current = ctx.payment
            if (
                current is None
                or current.status is not S.HOLD_ACTIVE
                or current.hold_until is None
                or now < current.hold_until
            ):
                return False
            target = next_status(current.status, Event.EXPIRE)
            ctx.put_payment(current.model_copy(update={"status": target, "updated_at": now}))
            return True

        if self._repo.transact(payment_id, apply):
            with self._operation(payment_id) as sink:
                sink.emit(
                    "orchestrator",
                    "STATE_CHANGE",
                    "Payment HOLD_ACTIVE -> HOLD_EXPIRED: hold elapsed; customer action required",
                    status=S.HOLD_EXPIRED.value,
                )
            self._audit("PAYMENT_EXPIRE", payment_id, "system")
        return self._load(payment_id, customer_id)

    def refresh(self, payment_id: str) -> PaymentDoc:
        return self._refresh(payment_id)

    # ------------------------------------------------------------------ create

    async def create_payment(
        self,
        customer_id: str,
        recipient: str,
        amount: int,
        note: str,
        idempotency_key: str,
    ) -> PaymentDoc:
        idem_id = idempotency_id(customer_id, idempotency_key)
        existing = self._repo.find_by_idempotency(idem_id)
        if existing:
            return self._refresh(existing, customer_id)

        customer = self._dataset.get_customer(customer_id)
        if customer is None:
            raise not_found("Customer not found.")
        if amount > customer.balance:
            raise validation_error("Insufficient balance for this payment.")
        resolved = resolve(self._dataset, recipient)

        now = self._clock()
        payment_id = new_payment_id()
        doc = PaymentDoc(
            id=payment_id,
            customer_id=customer_id,
            customer_name=customer.display_name,
            beneficiary_id=resolved.beneficiary_id,
            recipient_name=resolved.beneficiary.display_name if resolved.beneficiary else None,
            recipient_handle=resolved.handle,
            recipient_verified=resolved.verified,
            amount=amount,
            note=note,
            status=S.INITIATED,
            created_at=now,
            updated_at=now,
        )
        self._hub.begin_operation(payment_id)
        try:
            stored, created = self._repo.create(doc, idem_id)
            if not created:
                return self._refresh(stored.id, customer_id)
            sink = self._hub.sink(payment_id)
            sink.emit("orchestrator", "STARTED", "Payment created", status=S.INITIATED.value)
            self._audit("PAYMENT_CREATE", payment_id, customer_id)
            self._transition(payment_id, Event.ASSESS, sink, reason="assessment started")
            await self._guarded(payment_id, sink, self._assess(stored, sink))
        finally:
            self._hub.end_operation(payment_id)
        return self._load(payment_id, customer_id)

    async def _guarded(self, payment_id: str, sink: TraceSink, work: Awaitable[None]) -> None:
        """Unexpected failures fail safe to REVIEW rather than leaving the payment stuck."""
        try:
            await work
        except ApiError as exc:
            log.info("pipeline_skipped", extra={"payment_id": payment_id, "error_type": exc.code})
        except Exception as exc:
            log.error(
                "assessment_failed",
                extra={"payment_id": payment_id, "error_type": type(exc).__name__},
            )
            sink.emit(
                "orchestrator",
                "FAILED",
                "Assessment failed unexpectedly; routed to review",
                status="FAILED",
            )
            try:
                self._transition(
                    payment_id,
                    Event.REQUIRE_REVIEW,
                    sink,
                    customize=lambda d, _now: d.model_copy(
                        update={"explanation": _FALLBACK_EXPLANATION}
                    ),
                    reason="fail-safe",
                )
            except ApiError:
                pass

    def _context(self, doc: PaymentDoc) -> PaymentContext:
        return PaymentContext(
            payment_id=doc.id,
            customer_id=doc.customer_id,
            beneficiary_id=doc.beneficiary_id,
            amount=doc.amount,
            now=self._clock(),
        )

    # ------------------------------------------------------------------ assessment

    async def _assess(self, doc: PaymentDoc, sink: TraceSink) -> None:
        ctx = self._context(doc)
        started_at = self._clock()
        t0 = time.perf_counter()
        sink.emit("orchestrator", "STARTED", "Running fraud detectors")
        tool_calls: list[ToolCall] = []
        try:
            detected = await self._orch.run_detectors(ctx, sink)
            anomaly, network, tool_calls = (
                detected.anomaly,
                detected.fraud_network,
                detected.tool_calls,
            )
        except Exception as exc:
            log.error(
                "detectors_failed", extra={"payment_id": doc.id, "error_type": type(exc).__name__}
            )
            sink.emit(
                "orchestrator",
                "FAILED",
                "Detectors failed to run; treating checks as incomplete",
                status="FAILED",
            )
            anomaly, network = _failed("anomaly"), _failed("fraud_network")

        agg = aggregate(anomaly, network, None, self._config)
        findings = [anomaly, network]
        sink.emit(
            "policy",
            "COMPLETED",
            "Pre-assessment computed",
            status="OK",
            result_summary=(
                f"pre_score={agg.pre_score} elevated={agg.elevated} incomplete={agg.incomplete}"
            ),
        )

        needs_review_now = agg.incomplete and not agg.elevated
        explanation: Explanation | None = None
        if needs_review_now:
            explanation = await self._explain(ctx, findings, agg, sink)

        self._store_assessment(
            doc,
            "INITIAL",
            findings,
            agg,
            started_at,
            t0,
            tool_calls=tool_calls,
            explanation=explanation,
        )
        await self._record_signals(doc, findings)

        if agg.elevated:
            questions = await self._ask(ctx, findings, sink)
            if questions:
                self._transition(
                    doc.id,
                    Event.ELEVATED,
                    sink,
                    customize=lambda d, _now: d.model_copy(
                        update={"questions": questions, "aggregate": agg}
                    ),
                    reason="scam-check questions required",
                )
                return
            await self._finalize(doc, findings, tool_calls, [], [], None, sink)
            return
        if needs_review_now:
            self._transition(
                doc.id,
                Event.REQUIRE_REVIEW,
                sink,
                customize=lambda d, _now: d.model_copy(
                    update={"explanation": explanation, "aggregate": agg}
                ),
                reason="checks incomplete",
            )
            return
        self._transition(
            doc.id,
            Event.CLEARED,
            sink,
            customize=lambda d, _now: d.model_copy(update={"aggregate": agg}),
            reason="low risk",
        )

    async def _ask(
        self, ctx: PaymentContext, findings: list[AgentFinding], sink: TraceSink
    ) -> list[Question]:
        try:
            result = await self._orch.ask_questions(ctx, findings, sink)
        except Exception as exc:
            log.error(
                "questionnaire_failed",
                extra={"payment_id": ctx.payment_id, "error_type": type(exc).__name__},
            )
            sink.emit(
                "orchestrator",
                "FAILED",
                "Questionnaire unavailable; deciding without answers",
                status="FAILED",
            )
            return []
        return result.questions[:3]

    async def _explain(
        self, ctx: PaymentContext, findings: list[AgentFinding], agg: Aggregate, sink: TraceSink
    ) -> Explanation:
        try:
            return await self._orch.explain(ctx, findings, agg, sink)
        except Exception as exc:
            log.error(
                "explainer_failed",
                extra={"payment_id": ctx.payment_id, "error_type": type(exc).__name__},
            )
            sink.emit(
                "explainer",
                "FALLBACK",
                "Explanation unavailable; using generic text",
                status="DEGRADED",
            )
            return _FALLBACK_EXPLANATION

    async def _record_signals(self, doc: PaymentDoc, findings: list[AgentFinding]) -> None:
        evidence: list[Evidence] = [
            e
            for f in findings
            for e in f.evidence
            if e.points > 0 and e.provenance is not Provenance.USER_PROVIDED
        ]
        if not evidence:
            return
        try:
            await asyncio.to_thread(
                self._graph.record_signals, doc.id, doc.beneficiary_id, evidence
            )
        except Exception as exc:
            log.warning(
                "record_signals_failed",
                extra={"payment_id": doc.id, "error_type": type(exc).__name__},
            )

    def _store_assessment(
        self,
        doc: PaymentDoc,
        stage: str,
        findings: list[AgentFinding],
        agg: Aggregate,
        started_at: datetime,
        t0: float,
        *,
        tool_calls: list[ToolCall],
        questions: list[Question] | None = None,
        answers: list[Answer] | None = None,
        explanation: Explanation | None = None,
    ) -> None:
        assessment = Assessment(
            id=new_assessment_id(),
            stage=stage,
            created_at=self._clock(),
            complete=not agg.incomplete,
            findings=findings,
            aggregate=agg,
            config=self._config,
            questions=questions or [],
            answers=answers or [],
            explanation=explanation,
            model=self._orch.model_name,
            tool_calls=tool_calls,
            started_at=started_at,
            ended_at=self._clock(),
            duration_ms=_ms(t0),
        )
        self._repo.add_assessment(doc.id, doc.customer_id, assessment)

    # ------------------------------------------------------------------ answers

    async def submit_answers(
        self, customer_id: str, payment_id: str, answers: list[Answer]
    ) -> PaymentDoc:
        with self._operation(payment_id) as sink:
            doc = self._refresh(payment_id, customer_id)
            if doc.status is not S.QUESTIONNAIRE:
                raise invalid_transition("This payment is not waiting for answers.")
            self._validate_answers(doc.questions, answers)
            started_at = self._clock()
            self._transition(
                payment_id, Event.ANSWERS, sink, reason="answers received", actor=customer_id
            )
            await self._guarded(
                payment_id, sink, self._interpret_and_finalize(doc, answers, started_at, sink)
            )
        return self._load(payment_id, customer_id)

    @staticmethod
    def _validate_answers(questions: list[Question], answers: list[Answer]) -> None:
        by_id = {q.id: q for q in questions}
        seen: set[str] = set()
        for answer in answers:
            question = by_id.get(answer.question_id)
            if question is None or answer.question_id in seen:
                raise validation_error("Invalid request: answers.")
            if answer.option not in {o.value for o in question.options}:
                raise validation_error("Invalid request: answers.")
            if answer.free_text and not question.allow_free_text:
                raise validation_error("Invalid request: answers.")
            seen.add(answer.question_id)
        if seen != set(by_id):
            raise validation_error("Please answer every question.")

    async def _interpret_and_finalize(
        self, doc: PaymentDoc, answers: list[Answer], started_at: datetime, sink: TraceSink
    ) -> None:
        initial = next(
            (a for a in self._repo.assessments_for(doc.id) if a.stage == "INITIAL"), None
        )
        if initial is None:
            raise RuntimeError("initial assessment missing")
        by_agent = {f.agent_id: f for f in initial.findings}
        findings = [by_agent["anomaly"], by_agent["fraud_network"]]
        ctx = self._context(doc)
        try:
            result = await self._orch.interpret_answers(
                ctx, doc.questions, answers, findings, self._config, sink
            )
            questionnaire: AgentFinding | None = result.finding
        except Exception as exc:
            log.error(
                "interpret_failed", extra={"payment_id": doc.id, "error_type": type(exc).__name__}
            )
            sink.emit(
                "questionnaire",
                "FAILED",
                "Answers could not be interpreted; no context applied",
                status="FAILED",
            )
            questionnaire = None
        await self._finalize(
            doc,
            findings,
            initial.tool_calls,
            doc.questions,
            answers,
            questionnaire,
            sink,
            started_at,
        )

    async def _finalize(
        self,
        doc: PaymentDoc,
        findings: list[AgentFinding],
        tool_calls: list[ToolCall],
        questions: list[Question],
        answers: list[Answer],
        questionnaire: AgentFinding | None,
        sink: TraceSink,
        started_at: datetime | None = None,
    ) -> None:
        started = started_at or self._clock()
        t0 = time.perf_counter()
        anomaly = next(f for f in findings if f.agent_id == "anomaly")
        network = next(f for f in findings if f.agent_id == "fraud_network")
        agg = aggregate(anomaly, network, questionnaire, self._config)
        all_findings = [*findings, *([questionnaire] if questionnaire else [])]
        sink.emit(
            "policy",
            "COMPLETED",
            "Final policy decision",
            status="OK",
            result_summary=(
                f"final_score={agg.final_score} level={agg.level.value} action={agg.action.value}"
            ),
        )
        explanation: Explanation | None = None
        if agg.action is not Action.PROCEED:
            explanation = await self._explain(self._context(doc), all_findings, agg, sink)
        self._store_assessment(
            doc,
            "FINAL",
            all_findings,
            agg,
            started,
            t0,
            tool_calls=tool_calls,
            questions=questions,
            answers=answers,
            explanation=explanation,
        )

        def apply(d: PaymentDoc, now: datetime) -> PaymentDoc:
            update: dict[str, object] = {
                "aggregate": agg,
                "explanation": explanation,
                "questions": [],
            }
            if agg.action is Action.HOLD:
                update["hold_until"] = now + timedelta(seconds=self._config.hold_seconds)
            return d.model_copy(update=update)

        event = {
            Action.PROCEED: Event.CLEARED,
            Action.REVIEW: Event.REQUIRE_REVIEW,
            Action.HOLD: Event.REQUIRE_HOLD,
        }[agg.action]
        self._transition(
            doc.id, event, sink, customize=apply, reason=f"policy action {agg.action.value}"
        )

    # ------------------------------------------------------------------ simple actions

    def get(self, customer_id: str, payment_id: str) -> PaymentDoc:
        return self._refresh(payment_id, customer_id)

    async def acknowledge(self, customer_id: str, payment_id: str) -> PaymentDoc:
        with self._operation(payment_id) as sink:
            self._refresh(payment_id, customer_id)
            self._transition(
                payment_id,
                Event.ACKNOWLEDGE,
                sink,
                reason="warning acknowledged",
                actor=customer_id,
            )
        return self._load(payment_id, customer_id)

    async def verify(self, customer_id: str, payment_id: str) -> PaymentDoc:
        with self._operation(payment_id) as sink:
            doc = self._refresh(payment_id, customer_id)
            if doc.status is S.HOLD_ACTIVE:
                raise hold_active("This payment is on hold. Please wait for the hold to end.")
            if doc.status is not S.HOLD_EXPIRED:
                raise invalid_transition("There is nothing to verify for this payment.")
            now = self._clock()

            def apply(ctx: TxnContext) -> bool:
                current = ctx.payment
                if current is None or current.status is not S.HOLD_EXPIRED:
                    raise invalid_transition("There is nothing to verify for this payment.")
                if current.verified:
                    return False
                ctx.put_payment(current.model_copy(update={"verified": True, "updated_at": now}))
                return True

            if self._repo.transact(payment_id, apply):
                sink.emit(
                    "orchestrator",
                    "STATE_CHANGE",
                    "Customer confirmed independent verification",
                    status=S.HOLD_EXPIRED.value,
                )
                self._audit("PAYMENT_VERIFY", payment_id, customer_id)
        return self._load(payment_id, customer_id)

    async def continue_(self, customer_id: str, payment_id: str) -> PaymentDoc:
        def guard(doc: PaymentDoc) -> ApiError | None:
            if doc.status is S.HOLD_ACTIVE:
                return hold_active("This payment is on hold. Please wait for the hold to end.")
            if doc.status is S.HOLD_EXPIRED and not doc.verified:
                return invalid_transition(
                    "Confirm that you verified the recipient independently first."
                )
            return None

        with self._operation(payment_id) as sink:
            self._refresh(payment_id, customer_id)
            self._transition(
                payment_id,
                Event.CONTINUE,
                sink,
                guard=guard,
                reason="verified; continuing to authorization",
                actor=customer_id,
            )
        return self._load(payment_id, customer_id)

    async def cancel(self, customer_id: str, payment_id: str) -> PaymentDoc:
        with self._operation(payment_id) as sink:
            self._refresh(payment_id, customer_id)
            self._transition(
                payment_id, Event.CANCEL, sink, reason="cancelled by customer", actor=customer_id
            )
        return self._load(payment_id, customer_id)

    # ------------------------------------------------------------------ authorize / complete

    async def authorize(self, customer_id: str, payment_id: str, pin: str) -> PaymentDoc:
        if not PIN_FORMAT.match(pin):
            raise validation_error(
                "Invalid request: pin."
            )  # the PIN is only format-checked, never stored
        del pin
        with self._operation(payment_id) as sink:
            doc = self._refresh(payment_id, customer_id)
            if doc.status is S.HOLD_ACTIVE:
                raise hold_active("This payment is on hold. Please wait for the hold to end.")
            if doc.status is not S.READY_FOR_AUTH:
                raise invalid_transition("This payment is not ready to be authorized.")
            source = self._dataset.account_for_owner(customer_id)
            if source is None:
                raise RuntimeError("customer has no account")
            now = self._clock()
            txn = Transaction(
                id=payment_id,
                source_account_id=source.id,
                beneficiary_id=doc.beneficiary_id,
                amount=doc.amount,
                note=doc.note,
                timestamp=now,
            )

            def apply(ctx: TxnContext) -> PaymentDoc:
                current = ctx.payment
                if current is None:
                    raise not_found("Payment not found.")
                if current.status is not S.READY_FOR_AUTH:
                    raise invalid_transition("This payment is not ready to be authorized.")
                customer = ctx.customer(customer_id)
                if customer is None:
                    raise not_found("Customer not found.")
                if customer.balance < current.amount:
                    raise validation_error("Insufficient balance for this payment.")
                if current.beneficiary_id.startswith(UNVERIFIED_PREFIX) and not ctx.exists(
                    BENEFICIARIES, current.beneficiary_id
                ):
                    self._put_unverified_payee(ctx, current, now)
                updated = current.model_copy(
                    update={
                        "status": next_status(current.status, Event.AUTHORIZE),
                        "updated_at": now,
                        "transaction_id": payment_id,
                    }
                )
                ctx.put_payment(updated)
                ctx.put(
                    CUSTOMERS,
                    customer_id,
                    {"balance": customer.balance - current.amount},
                    merge=True,
                )
                ctx.put(TRANSACTIONS, payment_id, txn.model_dump(mode="python"))
                return updated

            completed = self._repo.transact(payment_id, apply)
            sink.emit(
                "orchestrator",
                "STATE_CHANGE",
                "Payment READY_FOR_AUTH -> COMPLETED: simulated authorization accepted",
                status=S.COMPLETED.value,
            )
            self._audit("PAYMENT_AUTHORIZE", payment_id, customer_id)
            await self._project(completed, txn, sink)
        return self._load(payment_id, customer_id)

    @staticmethod
    def _put_unverified_payee(ctx: TxnContext, doc: PaymentDoc, now: datetime) -> None:
        payee = Beneficiary(
            id=doc.beneficiary_id,
            display_name=doc.recipient_handle,
            handle=doc.recipient_handle,
            first_seen_at=now,
        )
        digits = doc.recipient_handle[-4:] if doc.recipient_handle.isdigit() else "0000"
        account = Account(
            id=account_id(doc.beneficiary_id),
            owner_id=doc.beneficiary_id,
            owner_type=OwnerType.BENEFICIARY,
            opened_at=now,
            account_number=str(500_000_000_000 + crc32(doc.beneficiary_id.encode()) % 100_000_000),
            masked_number=f"XXXXXX{digits}",
        )
        ctx.put(BENEFICIARIES, payee.id, payee.model_dump(mode="python"))
        ctx.put(ACCOUNTS, account.id, account.model_dump(mode="python"))

    async def _project(self, doc: PaymentDoc, txn: Transaction, sink: TraceSink) -> None:
        """Graph projection is best effort: a failure never undoes a completed payment."""
        try:
            await asyncio.to_thread(self._graph.project_transaction, txn)
        except Exception as exc:
            log.error(
                "projection_failed", extra={"payment_id": doc.id, "error_type": type(exc).__name__}
            )
            sink.emit(
                "orchestrator",
                "FAILED",
                "Graph projection failed; re-ingest to repair",
                status="FAILED",
            )
            self._audit("GRAPH_PROJECTION_FAILED", doc.id, "system")
