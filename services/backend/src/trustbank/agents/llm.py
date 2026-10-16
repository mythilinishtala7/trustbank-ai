"""Model backend: real Gemini through ADK, or any ADK `BaseLlm` (tests pass a scripted one)."""

import asyncio
import os
import uuid

from google.adk.agents import BaseAgent
from google.adk.models import BaseLlm
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.genai import types
from pydantic import BaseModel, ValidationError

from trustbank.config import Settings


class ModelOutputError(Exception):
    """The model returned nothing usable (empty, not JSON, or off-schema)."""


def build_model(settings: Settings) -> BaseLlm:
    # Vertex AI by default; a Gemini API key switches to the Gemini API.
    if os.environ.get("GOOGLE_API_KEY"):
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "FALSE")
    else:
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "TRUE")
    # One attempt: the orchestrator owns the timeout and the degraded fallback.
    return Gemini(model=settings.model_name, retry_options=types.HttpRetryOptions(attempts=1))


async def run_agent_text(agent: BaseAgent, message: str, timeout: float) -> str:
    """Run one ADK agent turn and return the text of its final response."""

    async def _run() -> str:
        app = "agents"
        runner = InMemoryRunner(agent=agent, app_name=app)
        session = await runner.session_service.create_session(
            app_name=app, user_id="system", session_id=uuid.uuid4().hex
        )
        text = ""
        async for event in runner.run_async(
            user_id="system",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        ):
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(p.text or "" for p in event.content.parts)
        return text

    return await asyncio.wait_for(_run(), timeout=timeout)


def parse_output[M: BaseModel](schema: type[M], text: str) -> M:
    try:
        return schema.model_validate_json(text.strip())
    except ValidationError as exc:
        raise ModelOutputError("model output failed schema validation") from exc
