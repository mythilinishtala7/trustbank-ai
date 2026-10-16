"""Trace sink: assigns per-payment seq, persists every event, wakes in-process SSE subscribers."""

import asyncio
import json
import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from typing import Any

from trustbank.contracts import TimelineAgent, TimelineType, TraceEvent
from trustbank.payments.repo import PaymentRepository

log = logging.getLogger("trustbank.trace")


def _json_safe(value: dict[str, Any] | None) -> dict[str, Any] | None:
    return None if value is None else dict(json.loads(json.dumps(value, default=str)))


class TraceHub:
    def __init__(self, repo: PaymentRepository, clock: Callable[[], datetime]) -> None:
        self._repo = repo
        self._clock = clock
        self._lock = threading.Lock()
        self._next_seq: dict[str, int] = {}
        self._waiters: dict[str, set[tuple[asyncio.AbstractEventLoop, asyncio.Event]]] = (
            defaultdict(set)
        )
        self._active: dict[str, int] = defaultdict(int)

    def sink(self, payment_id: str) -> "PaymentTraceSink":
        return PaymentTraceSink(self, payment_id)

    def append(self, payment_id: str, event_fields: dict[str, Any]) -> TraceEvent:
        # Persist under the lock so seq order equals storage order even across threads.
        with self._lock:
            seq = self._next_seq.get(payment_id)
            if seq is None:
                seq = self._repo.last_event_seq(payment_id) + 1
            event = TraceEvent(seq=seq, at=self._clock(), **event_fields)
            try:
                self._repo.add_event(payment_id, event)
            except Exception as exc:
                log.error(
                    "trace_persist_failed",
                    extra={"payment_id": payment_id, "error_type": type(exc).__name__},
                )
                raise
            self._next_seq[payment_id] = seq + 1
        self._notify(payment_id)
        return event

    def _notify(self, payment_id: str) -> None:
        for loop, event in list(self._waiters.get(payment_id, ())):
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:  # loop already closed
                self._waiters[payment_id].discard((loop, event))

    def subscribe(self, payment_id: str) -> asyncio.Event:
        event = asyncio.Event()
        self._waiters[payment_id].add((asyncio.get_running_loop(), event))
        return event

    def unsubscribe(self, payment_id: str, event: asyncio.Event) -> None:
        self._waiters[payment_id] = {w for w in self._waiters[payment_id] if w[1] is not event}
        if not self._waiters[payment_id]:
            del self._waiters[payment_id]

    def begin_operation(self, payment_id: str) -> None:
        with self._lock:
            self._active[payment_id] += 1

    def end_operation(self, payment_id: str) -> None:
        with self._lock:
            self._active[payment_id] -= 1
            if self._active[payment_id] <= 0:
                del self._active[payment_id]
        self._notify(payment_id)

    def is_active(self, payment_id: str) -> bool:
        with self._lock:
            return self._active.get(payment_id, 0) > 0


class PaymentTraceSink:
    """Implements contracts.TraceSink for one payment."""

    def __init__(self, hub: TraceHub, payment_id: str) -> None:
        self._hub = hub
        self._payment_id = payment_id

    def emit(
        self,
        agent_id: TimelineAgent,
        type: TimelineType,
        message: str,
        *,
        status: str | None = None,
        duration_ms: int | None = None,
        tool: str | None = None,
        parameters: dict[str, Any] | None = None,
        result_summary: str | None = None,
    ) -> None:
        try:
            self._hub.append(
                self._payment_id,
                {
                    "agent_id": agent_id,
                    "type": type,
                    "message": message,
                    "status": status,
                    "duration_ms": duration_ms,
                    "tool": tool,
                    "parameters": _json_safe(parameters),
                    "result_summary": result_summary,
                },
            )
        except Exception:  # a failing trace must never break the payment
            return
