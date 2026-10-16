"""Read-only graph queries used by the agents and the investigation console.

These return facts and measurements only. They never return a verdict; agents derive
indicators (with INFERRED provenance) from these measurements. No query reads RiskSignal nodes.
Every time-based query takes an explicit `as_of` so results are reproducible.
"""

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Any, Literal

from neo4j import Driver, RoutingControl
from pydantic import BaseModel, ConfigDict

Direction = Literal["forward", "backward"]
_NODE_LIMIT = 300


class _Result(BaseModel):
    model_config = ConfigDict(frozen=True)


class GraphNode(_Result):
    id: str
    label: str
    properties: dict[str, Any]


class GraphEdge(_Result):
    type: str
    source: str
    target: str
    properties: dict[str, Any]


class Subgraph(_Result):
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


class SenderSummary(_Result):
    window_hours: int
    distinct_senders: int
    transactions: int
    sender_account_ids: tuple[str, ...]


class FlowProfile(_Result):
    """Money movement through one account in the window ending at `as_of`."""

    account_id: str
    window_hours: int
    inbound_count: int
    inbound_amount: int
    outbound_count: int
    outbound_amount: int
    distinct_senders: int
    distinct_destinations: int
    velocity: int
    retention: float | None
    median_dwell_minutes: float | None
    matched_amount: int


class Hop(_Result):
    account_id: str
    beneficiary_id: str
    transaction_id: str
    amount: int
    gap_minutes: float
    timestamp: datetime


class ForwardingChain(_Result):
    """One trail of funds, each hop following the previous within `max_gap_minutes`.

    `ends_at_dead_end` (forward only): the last account in the trail has sent nothing onward.
    """

    start_transaction_id: str
    direction: Direction
    hops: tuple[Hop, ...]
    ends_at_dead_end: bool


def _weighted_median(pieces: Sequence[tuple[float, int]]) -> float | None:
    """Median of values, each weighted by an amount."""
    if not pieces:
        return None
    ordered = sorted(pieces)
    half = sum(w for _, w in ordered) / 2
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= half:
            return value
    return ordered[-1][0]


def fifo_dwell(
    inbound: Sequence[tuple[datetime, int]], outbound: Sequence[tuple[datetime, int]]
) -> list[tuple[float, int]]:
    """Match outflows to inflows first-in-first-out. Returns (dwell_minutes, amount) pieces."""
    arrivals = [ts for ts, _ in sorted(inbound)]
    left = [amount for _, amount in sorted(inbound)]
    head = 0
    pieces: list[tuple[float, int]] = []
    for out_ts, out_amount in sorted(outbound):
        remaining = out_amount
        while remaining > 0 and head < len(arrivals):
            if arrivals[head] > out_ts:
                break  # cannot forward money that has not arrived yet
            used = min(remaining, left[head])
            pieces.append(((out_ts - arrivals[head]).total_seconds() / 60, used))
            left[head] -= used
            remaining -= used
            if left[head] == 0:
                head += 1
    return pieces


class GraphService:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(query, params, routing_=RoutingControl.READ)
        return [r.data() for r in records]

    def get_node(self, node_id: str) -> GraphNode | None:
        rows = self._run(
            "MATCH (n {id: $id}) RETURN labels(n)[0] AS label, properties(n) AS props LIMIT 1",
            id=node_id,
        )
        return (
            GraphNode(id=node_id, label=rows[0]["label"], properties=rows[0]["props"])
            if rows
            else None
        )

    def neighbors(self, node_id: str, limit: int = 50) -> Subgraph:
        """Direct neighbours of a node, with the relationships that connect them."""
        rows = self._run(
            "MATCH (n {id: $id})-[r]-(m) "
            "RETURN labels(n)[0] AS nl, properties(n) AS np, "
            "labels(m)[0] AS ml, properties(m) AS mp, "
            "type(r) AS type, startNode(r).id AS src, endNode(r).id AS dst, properties(r) AS rp "
            "LIMIT $limit",
            id=node_id,
            limit=limit,
        )
        return self._assemble(rows)

    def transaction_neighborhood(self, transaction_id: str, depth: int = 2) -> Subgraph:
        """Subgraph around a transaction, for the console and agent evidence (capped)."""
        depth = max(1, min(depth, 4))
        rows = self._run(
            f"MATCH p=(t:Transaction {{id: $id}})-[*1..{depth}]-(n) "
            "WHERE ALL(x IN nodes(p)[1..] WHERE NOT x:Transaction) "
            "UNWIND relationships(p) AS r "
            "WITH DISTINCT r LIMIT $limit "
            "RETURN labels(startNode(r))[0] AS nl, properties(startNode(r)) AS np, "
            "labels(endNode(r))[0] AS ml, properties(endNode(r)) AS mp, "
            "type(r) AS type, startNode(r).id AS src, endNode(r).id AS dst, properties(r) AS rp",
            id=transaction_id,
            limit=_NODE_LIMIT,
        )
        return self._assemble(rows)

    @staticmethod
    def _assemble(rows: Sequence[dict[str, Any]]) -> Subgraph:
        nodes: dict[str, GraphNode] = {}
        edges: dict[tuple[str, str, str], GraphEdge] = {}
        for r in rows:
            for label, props in ((r["nl"], r["np"]), (r["ml"], r["mp"])):
                nodes.setdefault(
                    props["id"], GraphNode(id=props["id"], label=label, properties=props)
                )
            edges.setdefault(
                (r["type"], r["src"], r["dst"]),
                GraphEdge(type=r["type"], source=r["src"], target=r["dst"], properties=r["rp"]),
            )
        return Subgraph(nodes=tuple(nodes.values()), edges=tuple(edges.values()))

    def account_age_days(self, account_id: str, as_of: datetime) -> int | None:
        rows = self._run("MATCH (a:Account {id: $id}) RETURN a.opened_at AS opened", id=account_id)
        if not rows:
            return None
        opened: datetime = rows[0]["opened"].to_native()
        return (as_of - opened).days

    def _inbound(self, account_id: str, since: datetime, until: datetime) -> list[dict[str, Any]]:
        return self._run(
            "MATCH (:Account {id: $id})<-[:OWNS]-(:Beneficiary)<-[:PAID]-(t:Transaction)"
            "<-[:SENT]-(s:Account) "
            "WHERE t.timestamp > $since AND t.timestamp <= $until "
            "RETURN t.id AS id, t.amount AS amount, t.timestamp AS ts, s.id AS source ORDER BY ts",
            id=account_id,
            since=since,
            until=until,
        )

    def _outbound(self, account_id: str, since: datetime, until: datetime) -> list[dict[str, Any]]:
        return self._run(
            "MATCH (:Account {id: $id})-[:SENT]->(t:Transaction)-[:PAID]->(b:Beneficiary) "
            "WHERE t.timestamp > $since AND t.timestamp <= $until "
            "RETURN t.id AS id, t.amount AS amount, t.timestamp AS ts, b.id AS dest ORDER BY ts",
            id=account_id,
            since=since,
            until=until,
        )

    def recent_senders(self, account_id: str, window_hours: int, as_of: datetime) -> SenderSummary:
        rows = self._inbound(account_id, as_of - timedelta(hours=window_hours), as_of)
        senders = tuple(sorted({r["source"] for r in rows}))
        return SenderSummary(
            window_hours=window_hours,
            distinct_senders=len(senders),
            transactions=len(rows),
            sender_account_ids=senders,
        )

    def flow_profile(self, account_id: str, window_hours: int, as_of: datetime) -> FlowProfile:
        since = as_of - timedelta(hours=window_hours)
        inbound = self._inbound(account_id, since, as_of)
        outbound = self._outbound(account_id, since, as_of)
        in_total = sum(r["amount"] for r in inbound)
        out_total = sum(r["amount"] for r in outbound)
        pieces = fifo_dwell(
            [(r["ts"].to_native(), r["amount"]) for r in inbound],
            [(r["ts"].to_native(), r["amount"]) for r in outbound],
        )
        return FlowProfile(
            account_id=account_id,
            window_hours=window_hours,
            inbound_count=len(inbound),
            inbound_amount=in_total,
            outbound_count=len(outbound),
            outbound_amount=out_total,
            distinct_senders=len({r["source"] for r in inbound}),
            distinct_destinations=len({r["dest"] for r in outbound}),
            velocity=len(inbound) + len(outbound),
            retention=max(0.0, (in_total - out_total) / in_total) if in_total else None,
            median_dwell_minutes=_weighted_median(pieces),
            matched_amount=sum(w for _, w in pieces),
        )

    def forwarding_chain(
        self,
        account_id: str,
        direction: Direction,
        window_hours: int,
        as_of: datetime,
        max_hops: int = 5,
        max_gap_minutes: int = 30,
    ) -> list[ForwardingChain]:
        """Trails where funds are passed on within `max_gap_minutes` per hop.

        `forward`: for each inbound payment to the account, follow where the money went next.
        `backward`: for each outbound payment from the account, follow where it came from.
        """
        since = as_of - timedelta(hours=window_hours)
        gap = timedelta(minutes=max_gap_minutes)
        chains: list[ForwardingChain] = []
        if direction == "forward":
            starts = [
                (r["id"], r["ts"].to_native()) for r in self._inbound(account_id, since, as_of)
            ]
            for txn_id, ts in starts:
                hops, dead_end = self._follow_forward(account_id, ts, gap, max_hops, as_of)
                chains.append(self._chain(txn_id, direction, hops, dead_end))
        else:
            starts = [
                (r["id"], r["ts"].to_native()) for r in self._outbound(account_id, since, as_of)
            ]
            for txn_id, ts in starts:
                hops, dead_end = self._follow_backward(account_id, ts, gap, max_hops)
                chains.append(self._chain(txn_id, direction, hops, dead_end))
        return chains

    @staticmethod
    def _chain(
        txn_id: str, direction: Direction, hops: list[Hop], dead_end: bool
    ) -> ForwardingChain:
        return ForwardingChain(
            start_transaction_id=txn_id,
            direction=direction,
            hops=tuple(hops),
            ends_at_dead_end=dead_end,
        )

    def _has_outbound(self, account_id: str, as_of: datetime) -> bool:
        rows = self._run(
            "MATCH (:Account {id: $id})-[:SENT]->(t:Transaction) WHERE t.timestamp <= $until "
            "RETURN count(t) AS c",
            id=account_id,
            until=as_of,
        )
        return bool(rows[0]["c"])

    def _follow_forward(
        self, account_id: str, arrived: datetime, gap: timedelta, max_hops: int, as_of: datetime
    ) -> tuple[list[Hop], bool]:
        hops: list[Hop] = []
        current, when = account_id, arrived
        for _ in range(max_hops):
            rows = self._run(
                "MATCH (:Account {id: $id})-[:SENT]->(t:Transaction)-[:PAID]->(b:Beneficiary)"
                "-[:OWNS]->(next:Account) "
                "WHERE t.timestamp >= $after AND t.timestamp <= $until "
                "RETURN t.id AS id, t.amount AS amount, t.timestamp AS ts, "
                "b.id AS ben, next.id AS next "
                "ORDER BY ts LIMIT 1",
                id=current,
                after=when,
                until=min(when + gap, as_of),
            )
            if not rows:
                return hops, bool(hops) and not self._has_outbound(current, as_of)
            r = rows[0]
            ts = r["ts"].to_native()
            hops.append(
                Hop(
                    account_id=r["next"],
                    beneficiary_id=r["ben"],
                    transaction_id=r["id"],
                    amount=r["amount"],
                    gap_minutes=(ts - when).total_seconds() / 60,
                    timestamp=ts,
                )
            )
            current, when = r["next"], ts
        return hops, False

    def _follow_backward(
        self, account_id: str, sent_at: datetime, gap: timedelta, max_hops: int
    ) -> tuple[list[Hop], bool]:
        hops: list[Hop] = []
        current, when = account_id, sent_at
        for _ in range(max_hops):
            rows = self._run(
                "MATCH (:Account {id: $id})<-[:OWNS]-(b:Beneficiary)<-[:PAID]-(t:Transaction)"
                "<-[:SENT]-(prev:Account) "
                "WHERE t.timestamp <= $before AND t.timestamp >= $after "
                "RETURN t.id AS id, t.amount AS amount, t.timestamp AS ts, "
                "b.id AS ben, prev.id AS prev "
                "ORDER BY ts DESC LIMIT 1",
                id=current,
                before=when,
                after=when - gap,
            )
            if not rows:
                return hops, False
            r = rows[0]
            ts = r["ts"].to_native()
            hops.append(
                Hop(
                    account_id=r["prev"],
                    beneficiary_id=r["ben"],
                    transaction_id=r["id"],
                    amount=r["amount"],
                    gap_minutes=(when - ts).total_seconds() / 60,
                    timestamp=ts,
                )
            )
            current, when = r["prev"], ts
        return hops, False
