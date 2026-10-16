"""Typed results of `GraphService` queries. Facts and computed measurements only, never verdicts."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from trustbank.domain import Provenance


class _Result(BaseModel):
    model_config = ConfigDict(frozen=True)


class NodeResult(_Result):
    found: bool
    id: str
    label: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class Neighbor(_Result):
    id: str
    label: str
    name: str | None
    rel_type: str
    direction: str  # "out" or "in", relative to the queried node
    provenance: Provenance | None = None
    kind: str | None = None


class NeighborsResult(_Result):
    found: bool
    id: str
    neighbors: list[Neighbor] = Field(default_factory=list)
    truncated: bool = False


class Entity(_Result):
    id: str
    label: str
    name: str | None
    role: str  # why it is in the neighborhood


class Relationship(_Result):
    id: str
    source: str
    target: str
    type: str
    provenance: Provenance | None = None
    kind: str | None = None


class Neighborhood(_Result):
    found: bool
    transaction_id: str
    entities: list[Entity] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    highlighted_ids: list[str] = Field(default_factory=list)


class SenderSummary(_Result):
    found: bool
    account_id: str
    window_hours: int
    distinct_senders: int
    transaction_count: int
    total_amount: int
    sender_account_ids: list[str] = Field(default_factory=list)
    transaction_ids: list[str] = Field(default_factory=list)


class FlowProfile(_Result):
    found: bool
    account_id: str
    window_hours: int
    as_of: datetime
    inbound_count: int = 0
    inbound_total: int = 0
    outbound_count: int = 0
    outbound_total: int = 0
    distinct_senders: int = 0
    distinct_destinations: int = 0
    outflow_ratio: float | None = None
    retention_ratio: float | None = None  # share of inflow still in the account (FIFO)
    median_dwell_minutes: float | None = None  # amount-weighted, FIFO matched
    max_dwell_minutes: float | None = None
    velocity: int = 0  # transactions in the window, both directions
    regular_schedule: bool = False  # outflows on a fixed clock time or fixed interval
    destination_account_ids: list[str] = Field(default_factory=list)
    inbound_transaction_ids: list[str] = Field(default_factory=list)
    outbound_transaction_ids: list[str] = Field(default_factory=list)


class Hop(_Result):
    transaction_id: str
    from_account_id: str
    to_account_id: str
    amount: int
    at: datetime
    gap_minutes: float | None  # minutes after the previous hop (or the matching arrival)


class Chain(_Result):
    hops: list[Hop]
    terminal_account_id: str
    terminal_has_onward: bool


class ForwardingChains(_Result):
    found: bool
    account_id: str
    window_hours: int
    max_hops: int
    max_gap_minutes: int
    chains: list[Chain] = Field(default_factory=list)

    @property
    def max_depth(self) -> int:
        return max((len(c.hops) for c in self.chains), default=0)
