"""Scripted ADK model for tests. Agent code has no test-only branches: it just gets this BaseLlm."""

import asyncio
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Any

from google.adk.models import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import types


@dataclass
class Slow:
    seconds: float
    text: str


class ScriptedLlm(BaseLlm):
    """Plays `script` in order. Items: reply text, an Exception to raise, or `Slow`."""

    model: str = "scripted-stub"
    script: list[Any] = []
    prompts: list[str] = []
    instructions: list[str] = []

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        last = llm_request.contents[-1] if llm_request.contents else None
        self.prompts.append(
            "".join(p.text or "" for p in last.parts or []) if last and last.parts else ""
        )
        self.instructions.append(
            str(llm_request.config.system_instruction) if llm_request.config else ""
        )
        if not self.script:
            raise AssertionError("model called more often than scripted")
        item = self.script.pop(0)
        if isinstance(item, Slow):
            await asyncio.sleep(item.seconds)
            item = item.text
        if isinstance(item, Exception):
            raise item
        yield LlmResponse(content=types.Content(role="model", parts=[types.Part(text=item)]))


def scripted(*items: Any) -> ScriptedLlm:
    return ScriptedLlm(script=list(items), prompts=[], instructions=[])
