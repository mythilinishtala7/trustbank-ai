"""Records every tool call an agent makes and mirrors it to the timeline."""

import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from trustbank.contracts import ToolCall, TraceSink


class ToolRecorder:
    def __init__(self, trace: TraceSink) -> None:
        self._trace = trace
        self.calls: list[ToolCall] = []

    async def call[T](
        self,
        agent_id: str,
        tool: str,
        parameters: dict[str, Any],
        fn: Callable[[], T],
        summarize: Callable[[T], str],
    ) -> T:
        """Run a blocking tool off the event loop; record and emit once it returns."""
        started = datetime.now(UTC)
        t0 = time.perf_counter()
        try:
            result = await asyncio.to_thread(fn)
        except Exception as exc:
            self._record(agent_id, tool, parameters, f"error: {type(exc).__name__}", started, t0)
            raise
        self._record(agent_id, tool, parameters, summarize(result), started, t0)
        return result

    def _record(
        self,
        agent_id: str,
        tool: str,
        parameters: dict[str, Any],
        summary: str,
        started: datetime,
        t0: float,
    ) -> None:
        duration_ms = round((time.perf_counter() - t0) * 1000)
        self.calls.append(
            ToolCall(
                agent_id=agent_id,
                tool=tool,
                parameters=parameters,
                result_summary=summary,
                started_at=started,
                duration_ms=duration_ms,
            )
        )
        self._trace.emit(
            agent_id,  # type: ignore[arg-type]
            "TOOL_CALL",
            f"{tool} finished",
            duration_ms=duration_ms,
            tool=tool,
            parameters=parameters,
            result_summary=summary,
        )
