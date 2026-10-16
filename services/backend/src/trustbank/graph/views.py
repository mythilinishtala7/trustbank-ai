"""Console-facing graph view (camelCase API model)."""

from typing import Literal

from pydantic import Field

from trustbank.contracts import ApiModel
from trustbank.domain import Provenance

NodeLabel = Literal["Customer", "Account", "Transaction", "Beneficiary", "RiskSignal"]
EdgeType = Literal["OWNS", "SENT", "PAID", "CONNECTED_TO", "FLAGGED_FOR"]


class GraphNode(ApiModel):
    id: str
    label: NodeLabel
    name: str
    highlighted: bool = False
    properties: dict[str, str] = Field(default_factory=dict)


class GraphEdge(ApiModel):
    id: str
    source: str
    target: str
    type: EdgeType
    provenance: Provenance | None = None
    kind: str | None = None
    highlighted: bool = False


class GraphView(ApiModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    truncated: bool = False
