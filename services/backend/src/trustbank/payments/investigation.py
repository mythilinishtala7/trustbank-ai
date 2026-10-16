"""Read side for the investigation console: lookup, timeline polling and SSE streaming."""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Callable
from datetime import datetime

from trustbank.api.schemas import (
    InvestigationTransaction,
    TimelineResponse,
    TransactionListItem,
    TransactionSummary,
)
from trustbank.contracts import TERMINAL_STATUSES, TraceEvent
from trustbank.errors import not_found
from trustbank.graph import GraphService
from trustbank.graph.views import GraphView
from trustbank.payments.models import PaymentDoc
from trustbank.payments.repo import PaymentRepository
from trustbank.payments.service import PaymentService
from trustbank.payments.trace import TraceHub
from trustbank.store import DatasetRepository

log = logging.getLogger("trustbank.investigation")

MAX_GRAPH_NODES = 80


class InvestigationService:
    def __init__(
        self,
        *,
        payments: PaymentService,
        dataset: DatasetRepository,
        repo: PaymentRepository,
        graph: GraphService,
        hub: TraceHub,
        clock: Callable[[], datetime],
        ping_interval: float = 15.0,
        poll_interval: float = 1.0,
    ) -> None:
        self._payments = payments
        self._dataset = dataset
        self._repo = repo
        self._graph = graph
        self._hub = hub
        self._clock = clock
        self._ping_interval = ping_interval
        self._poll_interval = poll_interval

    def list_recent(self, limit: int) -> list[TransactionListItem]:
        items: list[TransactionListItem] = []
        for doc in self._repo.recent(limit):
            if doc.status.value == "HOLD_ACTIVE":
                doc = self._payments.refresh(doc.id)
            items.append(
                TransactionListItem(
                    transaction_id=doc.id,
                    customer_name=doc.customer_name,
                    recipient_name=doc.recipient_name or doc.recipient_handle,
                    amount=doc.amount,
                    status=doc.status.value,
                    created_at=doc.created_at,
                )
            )
        return items

    def _payment(self, transaction_id: str) -> PaymentDoc | None:
        if self._repo.get(transaction_id) is None:
            return None
        return self._payments.refresh(transaction_id)

    def audit_lookup(self, transaction_id: str, actor: str, found: bool) -> None:
        try:
            self._repo.audit(
                self._clock(),
                "INVESTIGATION_LOOKUP",
                actor,
                transaction_id=transaction_id,
                found="true" if found else "false",
            )
        except Exception as exc:
            log.error("audit_failed", extra={"error_type": type(exc).__name__})

    async def detail(self, transaction_id: str, actor: str) -> InvestigationTransaction:
        payment = await asyncio.to_thread(self._payment, transaction_id)
        if payment is not None:
            self.audit_lookup(transaction_id, actor, True)
            return await self._payment_detail(payment)
        historical = await asyncio.to_thread(self._historical, transaction_id)
        self.audit_lookup(transaction_id, actor, historical is not None)
        if historical is None:
            raise not_found("Transaction not found.")
        return historical

    async def _payment_detail(self, doc: PaymentDoc) -> InvestigationTransaction:
        assessments = await asyncio.to_thread(self._repo.assessments_for, doc.id)
        highlight = {
            entity
            for a in assessments
            for f in a.findings
            for e in f.evidence
            for entity in e.source_entity_ids
        }
        graph = await self._graph_view(
            customer_id=doc.customer_id,
            beneficiary_id=doc.beneficiary_id,
            transaction_id=doc.transaction_id,
            highlight=highlight,
        )
        return InvestigationTransaction(
            transaction_id=doc.id,
            kind="PAYMENT",
            summary=TransactionSummary(
                customer_id=doc.customer_id,
                customer_name=doc.customer_name,
                recipient_id=doc.beneficiary_id,
                recipient_name=doc.recipient_name or doc.recipient_handle,
                amount=doc.amount,
                note=doc.note,
                timestamp=doc.created_at,
                status=doc.status.value,
            ),
            assessments=assessments,
            graph=graph,
        )

    def _historical(self, transaction_id: str) -> InvestigationTransaction | None:
        txn = self._dataset.get_transaction(transaction_id)
        if txn is None:
            return None
        account = self._dataset.get_account(txn.source_account_id)
        owner_id = account.owner_id if account else txn.source_account_id
        customer = self._dataset.get_customer(owner_id)
        sender = customer or self._dataset.get_beneficiary(owner_id)
        recipient = self._dataset.get_beneficiary(txn.beneficiary_id)
        graph = self._graph_view_sync(
            customer_id=owner_id,
            beneficiary_id=txn.beneficiary_id,
            transaction_id=txn.id,
            highlight=set(),
        )
        return InvestigationTransaction(
            transaction_id=txn.id,
            kind="HISTORICAL",
            summary=TransactionSummary(
                customer_id=owner_id,
                customer_name=sender.display_name if sender else owner_id,
                recipient_id=txn.beneficiary_id,
                recipient_name=recipient.display_name if recipient else txn.beneficiary_id,
                amount=txn.amount,
                note=txn.note,
                timestamp=txn.timestamp,
                status=txn.status.value,
            ),
            assessments=[],
            graph=graph,
        )

    def _graph_view_sync(
        self,
        *,
        customer_id: str,
        beneficiary_id: str,
        transaction_id: str | None,
        highlight: set[str],
    ) -> GraphView:
        try:
            return self._graph.investigation_graph(
                customer_id=customer_id,
                beneficiary_id=beneficiary_id,
                transaction_id=transaction_id,
                highlight_ids=highlight,
                max_nodes=MAX_GRAPH_NODES,
            )
        except Exception as exc:
            # Stored assessments stay useful when Neo4j is down; the console shows an empty graph.
            log.error("graph_unavailable", extra={"error_type": type(exc).__name__})
            return GraphView()

    async def _graph_view(
        self,
        *,
        customer_id: str,
        beneficiary_id: str,
        transaction_id: str | None,
        highlight: set[str],
    ) -> GraphView:
        return await asyncio.to_thread(
            self._graph_view_sync,
            customer_id=customer_id,
            beneficiary_id=beneficiary_id,
            transaction_id=transaction_id,
            highlight=highlight,
        )

    # ------------------------------------------------------------------ timeline

    def _is_settled(self, doc: PaymentDoc) -> bool:
        return not self._hub.is_active(doc.id)

    async def timeline(self, transaction_id: str, after: int) -> TimelineResponse:
        doc = await asyncio.to_thread(self._payment, transaction_id)
        if doc is None:
            if await asyncio.to_thread(self._dataset.get_transaction, transaction_id) is None:
                raise not_found("Transaction not found.")
            return TimelineResponse(
                transaction_id=transaction_id, payment_status=None, done=True, events=[]
            )
        settled = self._is_settled(doc)
        events = await asyncio.to_thread(self._repo.events_after, doc.id, after)
        return TimelineResponse(
            transaction_id=doc.id,
            payment_status=doc.status.value,
            done=settled or doc.status in TERMINAL_STATUSES,
            events=events,
        )

    async def open_stream(self, transaction_id: str, after: int) -> AsyncIterator[str]:
        """Validate the id first (so unknown ids get a normal 404), then return the SSE frames."""
        doc = await asyncio.to_thread(self._payment, transaction_id)
        if doc is None:
            if await asyncio.to_thread(self._dataset.get_transaction, transaction_id) is None:
                raise not_found("Transaction not found.")
            return _single(_done_frame(transaction_id, None))
        return self._frames(doc.id, after)

    async def _frames(self, payment_id: str, after: int) -> AsyncIterator[str]:
        """`done` is sent once no more events are expected until the customer acts."""
        wake = self._hub.subscribe(payment_id)
        last_seq = after
        last_output = time.monotonic()
        try:
            while True:
                # Read the flag before the events: anything emitted before it cleared is persisted.
                settled = not self._hub.is_active(payment_id)
                events = await asyncio.to_thread(self._repo.events_after, payment_id, last_seq)
                for event in events:
                    yield _event_frame(event)
                    last_seq = event.seq
                    last_output = time.monotonic()
                if events:
                    continue
                if settled:
                    current = await asyncio.to_thread(self._repo.get, payment_id)
                    yield _done_frame(payment_id, current.status.value if current else None)
                    return
                try:
                    await asyncio.wait_for(wake.wait(), timeout=self._poll_interval)
                except TimeoutError:
                    pass
                wake.clear()
                if time.monotonic() - last_output >= self._ping_interval:
                    yield ": ping\n\n"
                    last_output = time.monotonic()
        finally:
            self._hub.unsubscribe(payment_id, wake)


async def _single(frame: str) -> AsyncIterator[str]:
    yield frame


def _event_frame(event: TraceEvent) -> str:
    return f"id: {event.seq}\nevent: timeline\ndata: {event.model_dump_json(by_alias=True)}\n\n"


def _done_frame(transaction_id: str, status: str | None) -> str:
    payload = json.dumps({"transactionId": transaction_id, "paymentStatus": status})
    return f"event: done\ndata: {payload}\n\n"
