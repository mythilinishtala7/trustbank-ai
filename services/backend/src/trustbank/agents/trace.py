"""Ordered record of tool calls an agent made, kept for the assessment record."""

from typing import Any

from pydantic import BaseModel, ConfigDict


class ToolCall(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_id: str
    tool: str
    params: dict[str, Any]
    result_summary: str


class ToolRecorder:
    """Collects tool calls and the entity ids those tools returned (used to ground evidence)."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self.calls: list[ToolCall] = []
        self.entity_ids: set[str] = set()

    def record(
        self, tool: str, params: dict[str, Any], summary: str, entity_ids: set[str] | None = None
    ) -> None:
        self.calls.append(
            ToolCall(agent_id=self.agent_id, tool=tool, params=params, result_summary=summary)
        )
        self.entity_ids |= entity_ids or set()
