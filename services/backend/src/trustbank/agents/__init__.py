from google.adk.models import BaseLlm

from trustbank.agents.anomaly import HistoryReader
from trustbank.agents.llm import build_model
from trustbank.agents.orchestrator import AdkOrchestrator
from trustbank.config import Settings
from trustbank.contracts import Orchestrator
from trustbank.graph import GraphService


def build_orchestrator(
    settings: Settings,
    graph: GraphService,
    repo: HistoryReader,
    model: BaseLlm | None = None,
) -> Orchestrator:
    """ADK orchestrator. `model` defaults to Gemini; tests pass a scripted `BaseLlm`."""
    return AdkOrchestrator(model=model or build_model(settings), graph=graph, history=repo)


__all__ = ["AdkOrchestrator", "build_orchestrator"]
