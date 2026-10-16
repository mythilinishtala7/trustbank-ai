"""Read-only graph queries over Neo4j (plus idempotent projection of new facts and signals).

Every Cypher value is a parameter. Detection queries never read `RiskSignal` nodes; only the
console view does.
"""

from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from neo4j import Driver, RoutingControl

from trustbank.config import Settings
from trustbank.contracts import Evidence
from trustbank.domain import Provenance, Transaction
from trustbank.graph.common import FACT, build_driver, plain_datetime
from trustbank.graph.flow import Movement, fifo_dwell, is_regular_schedule
from trustbank.graph.results import (
    Chain,
    Entity,
    FlowProfile,
    ForwardingChains,
    Hop,
    Neighbor,
    Neighborhood,
    NeighborsResult,
    NodeResult,
    Relationship,
    SenderSummary,
)
from trustbank.graph.schema import NODE_LABELS, REL_TYPES
from trustbank.graph.views import EdgeType, GraphEdge, GraphNode, GraphView, NodeLabel

_MAX_HOPS = 4
_QUERY_LIMIT = 2000
_CHAIN_LIMIT = 50


def _native(value: Any) -> Any:
    to_native = getattr(value, "to_native", None)
    return to_native() if callable(to_native) else value


def _utc(value: Any) -> datetime:
    dt: datetime = _native(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _text(value: Any) -> str:
    value = _native(value)
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _provenance(value: Any) -> Provenance | None:
    return Provenance(value) if value else None


class GraphService:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def close(self) -> None:
        self._driver.close()

    def _read(self, query: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(query, params, routing_=RoutingControl.READ)
        return [r.data() for r in records]

    def _write(self, query: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(query, params)
        return [r.data() for r in records]

    def ping(self) -> bool:
        try:
            self._driver.execute_query("RETURN 1", routing_=RoutingControl.READ)
        except Exception:
            return False
        return True

    # --- point lookups -------------------------------------------------------------------------

    def get_node(self, node_id: str) -> NodeResult:
        rows = self._read(
            """
            MATCH (n {id: $id}) WHERE any(l IN labels(n) WHERE l IN $labels)
            RETURN labels(n)[0] AS label, n AS props LIMIT 1
            """,
            id=node_id,
            labels=list(NODE_LABELS),
        )
        if not rows:
            return NodeResult(found=False, id=node_id)
        props = {k: _text(v) if hasattr(v, "to_native") else v for k, v in rows[0]["props"].items()}
        return NodeResult(found=True, id=node_id, label=rows[0]["label"], properties=props)

    def neighbors(
        self, node_id: str, rel_types: Sequence[str] | None = None, limit: int = 50
    ) -> NeighborsResult:
        if rel_types is not None and not set(rel_types) <= set(REL_TYPES):
            raise ValueError(
                f"unknown relationship types: {sorted(set(rel_types) - set(REL_TYPES))}"
            )
        types = list(rel_types) if rel_types else list(REL_TYPES)
        if not self.get_node(node_id).found:
            return NeighborsResult(found=False, id=node_id)
        rows = self._read(
            """
            MATCH (n {id: $id})-[r]-(m)
            WHERE type(r) IN $types AND any(l IN labels(m) WHERE l IN $labels)
            RETURN m.id AS id, labels(m)[0] AS label, m.name AS name, type(r) AS rel,
                   CASE WHEN startNode(r) = n THEN 'out' ELSE 'in' END AS direction,
                   r.provenance AS provenance, r.kind AS kind
            ORDER BY rel, id LIMIT $limit
            """,
            id=node_id,
            types=types,
            labels=list(NODE_LABELS),
            limit=limit + 1,
        )
        return NeighborsResult(
            found=True,
            id=node_id,
            truncated=len(rows) > limit,
            neighbors=[
                Neighbor(
                    id=r["id"],
                    label=r["label"],
                    name=r["name"],
                    rel_type=r["rel"],
                    direction=r["direction"],
                    provenance=_provenance(r["provenance"]),
                    kind=r["kind"],
                )
                for r in rows[:limit]
            ],
        )

    def account_for_owner(self, owner_id: str) -> str | None:
        rows = self._read(
            "MATCH (o {id: $id})-[:OWNS]->(a:Account) WHERE o:Customer OR o:Beneficiary "
            "RETURN a.id AS id LIMIT 1",
            id=owner_id,
        )
        return str(rows[0]["id"]) if rows else None

    def account_age_days(self, account_id: str, as_of: datetime) -> int | None:
        rows = self._read("MATCH (a:Account {id: $id}) RETURN a.openedAt AS opened", id=account_id)
        if not rows:
            return None
        return max(0, (as_of - _utc(rows[0]["opened"])).days)

    # --- flows ---------------------------------------------------------------------------------

    def _inbound(self, account_id: str, start: datetime, end: datetime) -> list[Movement]:
        rows = self._read(
            """
            MATCH (:Account {id: $id})<-[:OWNS]-(b:Beneficiary)<-[:PAID]-(t:Transaction)
            WHERE t.timestamp >= $start AND t.timestamp <= $end
            MATCH (s:Account)-[:SENT]->(t)
            RETURN t.id AS id, t.amount AS amount, t.timestamp AS at, s.id AS other
            ORDER BY t.timestamp, t.id LIMIT $limit
            """,
            id=account_id,
            start=start,
            end=end,
            limit=_QUERY_LIMIT,
        )
        return [Movement(r["id"], _utc(r["at"]), r["amount"], r["other"]) for r in rows]

    def _outbound(
        self, account_ids: Sequence[str], start: datetime, end: datetime
    ) -> list[dict[str, Any]]:
        rows = self._read(
            """
            MATCH (s:Account)-[:SENT]->(t:Transaction)-[:PAID]->(:Beneficiary)-[:OWNS]->(d:Account)
            WHERE s.id IN $ids AND t.timestamp >= $start AND t.timestamp <= $end
            RETURN t.id AS id, t.amount AS amount, t.timestamp AS at, s.id AS source, d.id AS dest
            ORDER BY t.timestamp, t.id LIMIT $limit
            """,
            ids=list(account_ids),
            start=start,
            end=end,
            limit=_QUERY_LIMIT,
        )
        return [r | {"at": _utc(r["at"])} for r in rows]

    def recent_senders(self, account_id: str, window_hours: int, as_of: datetime) -> SenderSummary:
        inbound = self._inbound(account_id, as_of - timedelta(hours=window_hours), as_of)
        senders = sorted({m.counterparty for m in inbound})
        return SenderSummary(
            found=self.get_node(account_id).found,
            account_id=account_id,
            window_hours=window_hours,
            distinct_senders=len(senders),
            transaction_count=len(inbound),
            total_amount=sum(m.amount for m in inbound),
            sender_account_ids=senders,
            transaction_ids=[m.id for m in inbound],
        )

    def flow_profile(self, account_id: str, window_hours: int, as_of: datetime) -> FlowProfile:
        if self.account_age_days(account_id, as_of) is None:
            return FlowProfile(
                found=False, account_id=account_id, window_hours=window_hours, as_of=as_of
            )
        start = as_of - timedelta(hours=window_hours)
        inbound = self._inbound(account_id, start, as_of)
        outbound = [
            Movement(r["id"], r["at"], r["amount"], r["dest"])
            for r in self._outbound([account_id], start, as_of)
        ]
        fifo = fifo_dwell(inbound, outbound)
        inflow, outflow = sum(m.amount for m in inbound), sum(m.amount for m in outbound)
        return FlowProfile(
            found=True,
            account_id=account_id,
            window_hours=window_hours,
            as_of=as_of,
            inbound_count=len(inbound),
            inbound_total=inflow,
            outbound_count=len(outbound),
            outbound_total=outflow,
            distinct_senders=len({m.counterparty for m in inbound}),
            distinct_destinations=len({m.counterparty for m in outbound}),
            outflow_ratio=outflow / inflow if inflow else None,
            retention_ratio=fifo.retention_ratio,
            median_dwell_minutes=fifo.median_dwell_minutes,
            max_dwell_minutes=fifo.max_dwell_minutes,
            velocity=len(inbound) + len(outbound),
            regular_schedule=is_regular_schedule(outbound),
            destination_account_ids=sorted({m.counterparty for m in outbound}),
            inbound_transaction_ids=[m.id for m in inbound],
            outbound_transaction_ids=[m.id for m in outbound],
        )

    def forwarding_chain(
        self,
        account_id: str,
        window_hours: int,
        as_of: datetime,
        max_hops: int = 3,
        max_gap_minutes: int = 15,
    ) -> ForwardingChains:
        max_hops = min(max_hops, _MAX_HOPS)
        found = self.account_age_days(account_id, as_of) is not None
        empty = ForwardingChains(
            found=found,
            account_id=account_id,
            window_hours=window_hours,
            max_hops=max_hops,
            max_gap_minutes=max_gap_minutes,
        )
        if not found:
            return empty

        start = as_of - timedelta(hours=window_hours)
        by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        frontier, seen = [account_id], {account_id}
        for _ in range(max_hops + 1):
            if not frontier:
                break
            for row in self._outbound(frontier, start, as_of):
                by_source[row["source"]].append(row)
            frontier = sorted({r["dest"] for a in frontier for r in by_source[a]} - seen)
            seen.update(frontier)

        inbound = self._inbound(account_id, start, as_of)
        gap = timedelta(minutes=max_gap_minutes)

        def entry_gap(first: dict[str, Any]) -> float | None:
            arrivals = [m.at for m in inbound if m.at <= first["at"]]
            return (first["at"] - max(arrivals)).total_seconds() / 60 if arrivals else None

        def onward(hop: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                r for r in by_source.get(hop["dest"], []) if hop["at"] <= r["at"] <= hop["at"] + gap
            ]

        chains: list[Chain] = []
        for first in by_source.get(account_id, []):
            path = [first]
            while len(path) < max_hops:
                nxt = onward(path[-1])
                if not nxt:
                    break
                path.append(nxt[0])
            last = path[-1]
            hops = [
                Hop(
                    transaction_id=h["id"],
                    from_account_id=h["source"],
                    to_account_id=h["dest"],
                    amount=h["amount"],
                    at=h["at"],
                    gap_minutes=entry_gap(h)
                    if i == 0
                    else (h["at"] - path[i - 1]["at"]).total_seconds() / 60,
                )
                for i, h in enumerate(path)
            ]
            chains.append(
                Chain(
                    hops=hops,
                    terminal_account_id=last["dest"],
                    terminal_has_onward=bool(
                        [r for r in by_source.get(last["dest"], []) if r["at"] > last["at"]]
                    ),
                )
            )
            if len(chains) >= _CHAIN_LIMIT:
                break
        return empty.model_copy(update={"chains": chains})

    # --- neighborhoods -------------------------------------------------------------------------

    def _owners(self, account_ids: Collection[str]) -> dict[str, tuple[str, str, str | None]]:
        rows = self._read(
            """
            MATCH (o)-[:OWNS]->(a:Account) WHERE a.id IN $ids AND (o:Customer OR o:Beneficiary)
            RETURN a.id AS account, o.id AS id, labels(o)[0] AS label, o.name AS name
            """,
            ids=list(account_ids),
        )
        return {r["account"]: (r["id"], r["label"], r["name"]) for r in rows}

    def _downstream(self, account_id: str, hops: int, per_level: int) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        frontier, seen = [account_id], {account_id}
        for level in range(1, hops + 1):
            if not frontier:
                break
            rows = self._read(
                """
                MATCH (s:Account)-[:SENT]->(t:Transaction)-[:PAID]->(b:Beneficiary)
                MATCH (b)-[:OWNS]->(d:Account)
                WHERE s.id IN $ids
                RETURN s.id AS source, t.id AS txn, t.amount AS amount, t.timestamp AS at,
                       b.id AS beneficiary, d.id AS dest
                ORDER BY t.timestamp DESC, t.id LIMIT $limit
                """,
                ids=frontier,
                limit=per_level,
            )
            out.extend(r | {"level": level} for r in rows)
            frontier = sorted({r["dest"] for r in rows} - seen)
            seen.update(frontier)
        return out

    def transaction_neighborhood(self, transaction_id: str, hops: int = 3) -> Neighborhood:
        rows = self._read(
            """
            MATCH (sa:Account)-[:SENT]->(t:Transaction {id: $id})-[:PAID]->(b:Beneficiary)
            OPTIONAL MATCH (b)-[:OWNS]->(ba:Account)
            RETURN sa.id AS sender_account, b.id AS beneficiary, b.name AS beneficiary_name,
                   ba.id AS beneficiary_account
            """,
            id=transaction_id,
        )
        if not rows:
            return Neighborhood(found=False, transaction_id=transaction_id)
        row = rows[0]
        hops = min(hops, 3)
        entities: dict[str, Entity] = {}
        rels: dict[str, Relationship] = {}
        highlighted = {transaction_id, row["beneficiary"], row["beneficiary_account"]}

        def add(entity_id: str, label: str, name: str | None, role: str) -> None:
            entities.setdefault(entity_id, Entity(id=entity_id, label=label, name=name, role=role))

        def rel(rid: str, source: str, target: str, rel_type: str, **extra: Any) -> None:
            rels.setdefault(
                rid,
                Relationship(
                    id=rid,
                    source=source,
                    target=target,
                    type=rel_type,
                    provenance=_provenance(extra.get("provenance") or FACT),
                    kind=extra.get("kind"),
                ),
            )

        t_node = self.get_node(transaction_id)
        add(transaction_id, "Transaction", f"₹{t_node.properties.get('amount', 0):,}", "assessed")
        accounts = {row["sender_account"], row["beneficiary_account"]} - {None}
        downstream = (
            self._downstream(row["beneficiary_account"], hops, 10)
            if row["beneficiary_account"]
            else []
        )
        connections = (
            self._read(
                """
                MATCH (a:Account {id: $id})-[c:CONNECTED_TO]-(x:Account)
                RETURN c.id AS id, startNode(c).id AS source, endNode(c).id AS target,
                       c.kind AS kind, c.provenance AS provenance, x.id AS other
                """,
                id=row["beneficiary_account"],
            )
            if row["beneficiary_account"]
            else []
        )
        accounts |= {d["dest"] for d in downstream} | {c["other"] for c in connections}
        owners = self._owners(accounts)

        for account_id in accounts:
            owner = owners.get(account_id)
            role = "sender" if account_id == row["sender_account"] else "account"
            add(account_id, "Account", account_id, role)
            if owner:
                add(owner[0], owner[1], owner[2], role)
                rel(f"own_{account_id}", owner[0], account_id, "OWNS")
        rel(f"sent_{transaction_id}", row["sender_account"], transaction_id, "SENT")
        rel(f"paid_{transaction_id}", transaction_id, row["beneficiary"], "PAID")
        for c in connections:
            rel(
                c["id"],
                c["source"],
                c["target"],
                "CONNECTED_TO",
                kind=c["kind"],
                provenance=c["provenance"],
            )
            highlighted |= {c["other"], c["id"]}
        for d in downstream:
            add(d["txn"], "Transaction", f"₹{d['amount']:,}", f"hop {d['level']}")
            rel(f"sent_{d['txn']}", d["source"], d["txn"], "SENT")
            rel(f"paid_{d['txn']}", d["txn"], d["beneficiary"], "PAID")
            highlighted |= {d["txn"], d["dest"]}
        return Neighborhood(
            found=True,
            transaction_id=transaction_id,
            entities=list(entities.values()),
            relationships=list(rels.values()),
            highlighted_ids=sorted(h for h in highlighted if h),
        )

    # --- writes: projection and signals --------------------------------------------------------

    def project_transaction(self, txn: Transaction) -> bool:
        """Idempotently add a completed transaction. False when an endpoint is missing."""
        rows = self._write(
            """
            MATCH (a:Account {id: $account}), (b:Beneficiary {id: $beneficiary})
            MERGE (t:Transaction {id: $id})
            SET t.amount = $amount, t.currency = $currency, t.note = $note,
                t.timestamp = $timestamp, t.status = $status
            MERGE (a)-[s:SENT {id: 'sent_' + $id}]->(t) SET s.provenance = $fact
            MERGE (t)-[p:PAID {id: 'paid_' + $id}]->(b) SET p.provenance = $fact
            RETURN t.id AS id
            """,
            id=txn.id,
            account=txn.source_account_id,
            beneficiary=txn.beneficiary_id,
            amount=txn.amount,
            currency=txn.currency,
            note=txn.note,
            timestamp=plain_datetime(txn.timestamp),
            status=txn.status.value,
            fact=FACT,
        )
        return bool(rows)

    def record_signals(
        self, transaction_id: str, beneficiary_id: str, evidence: list[Evidence]
    ) -> int:
        """Persist INFERRED network indicators as RiskSignal nodes. Outputs only, never read back
        by detection. Returns the number of signals written."""
        signals = [
            {
                "id": f"sig_{beneficiary_id}_{e.id.split('.', 1)[1]}",
                "code": e.id.split(".", 1)[1],
                "summary": e.summary,
                "points": e.points,
                "txns": sorted({*e.source_entity_ids, transaction_id}),
            }
            for e in evidence
            if e.provenance is Provenance.INFERRED and e.points > 0 and e.id.startswith("network.")
        ]
        if not signals:
            return 0
        self._write(
            """
            UNWIND $signals AS s
            MERGE (r:RiskSignal {id: s.id})
            SET r.code = s.code, r.summary = s.summary, r.points = s.points,
                r.provenance = 'INFERRED', r.beneficiaryId = $beneficiary, r.assessedAt = $now
            WITH r, s
            UNWIND s.txns AS tid
            MATCH (t:Transaction {id: tid})
            MERGE (t)-[f:FLAGGED_FOR {id: 'flag_' + tid + '_' + r.id}]->(r)
            SET f.provenance = 'INFERRED'
            """,
            signals=signals,
            beneficiary=beneficiary_id,
            now=datetime.now(UTC),
        )
        return len(signals)

    # --- console view --------------------------------------------------------------------------

    def investigation_graph(
        self,
        *,
        customer_id: str,
        beneficiary_id: str,
        transaction_id: str | None,
        highlight_ids: Collection[str],
        max_nodes: int = 80,
    ) -> GraphView:
        """Bounded neighborhood of the recipient plus the payer. Never the whole network."""
        builder = _ViewBuilder(max_nodes, set(highlight_ids))

        payer_account = self.account_for_owner(customer_id)
        recipient_account = self.account_for_owner(beneficiary_id)
        self._add_owned(builder, customer_id, payer_account)
        self._add_owned(builder, beneficiary_id, recipient_account)

        shown = bool(transaction_id) and self._add_transaction(builder, str(transaction_id))
        if not shown and payer_account and recipient_account:
            earlier = self._read(
                """
                MATCH (:Account {id: $payer})-[:SENT]->(t:Transaction)
                MATCH (t)-[:PAID]->(:Beneficiary {id: $ben})
                RETURN t.id AS id ORDER BY t.timestamp DESC LIMIT 3
                """,
                payer=payer_account,
                ben=beneficiary_id,
            )
            for r in earlier:
                self._add_transaction(builder, r["id"])

        if recipient_account:
            self._add_connections(builder, recipient_account)
            self._add_downstream(builder, recipient_account)
            self._add_inflows(builder, beneficiary_id)
            self._add_signals(builder, beneficiary_id)
        return builder.build()

    def _add_owned(self, b: "_ViewBuilder", owner_id: str, account_id: str | None) -> None:
        node = self.get_node(owner_id)
        if not node.found or node.label is None:
            return
        b.node(owner_id, node.label, str(node.properties.get("name", owner_id)), node.properties)
        if account_id:
            self._add_account(b, account_id)
            b.edge(f"own_{account_id}", owner_id, account_id, "OWNS", FACT)

    def _add_account(self, b: "_ViewBuilder", account_id: str) -> None:
        props = self.get_node(account_id).properties
        b.node(account_id, "Account", f"Account {props.get('maskedNumber', account_id)}", props)

    def _add_owner_of(self, b: "_ViewBuilder", account_id: str) -> None:
        owner = self._owners([account_id]).get(account_id)
        if owner:
            self._add_account(b, account_id)
            props = self.get_node(owner[0]).properties
            if b.node(owner[0], owner[1], owner[2] or owner[0], props):
                b.edge(f"own_{account_id}", owner[0], account_id, "OWNS", FACT)

    def _add_transaction(self, b: "_ViewBuilder", transaction_id: str) -> bool:
        rows = self._read(
            """
            MATCH (sa:Account)-[:SENT]->(t:Transaction {id: $id})-[:PAID]->(ben:Beneficiary)
            RETURN sa.id AS account, ben.id AS beneficiary
            """,
            id=transaction_id,
        )
        if not rows:
            return False
        props = self.get_node(transaction_id).properties
        if not b.node(transaction_id, "Transaction", f"₹{props.get('amount', 0):,}", props):
            return True
        self._add_owner_of(b, rows[0]["account"])
        b.edge(f"sent_{transaction_id}", rows[0]["account"], transaction_id, "SENT", FACT)
        b.edge(f"paid_{transaction_id}", transaction_id, rows[0]["beneficiary"], "PAID", FACT)
        return True

    def _add_connections(self, b: "_ViewBuilder", account_id: str) -> None:
        rows = self._read(
            """
            MATCH (a:Account {id: $id})-[c:CONNECTED_TO]-(x:Account)
            RETURN c.id AS id, startNode(c).id AS source, endNode(c).id AS target,
                   c.kind AS kind, c.provenance AS provenance, x.id AS other
            ORDER BY c.id LIMIT 5
            """,
            id=account_id,
        )
        for r in rows:
            self._add_owner_of(b, r["other"])
            b.edge(r["id"], r["source"], r["target"], "CONNECTED_TO", r["provenance"], r["kind"])

    def _add_downstream(self, b: "_ViewBuilder", account_id: str) -> None:
        for hop in self._downstream(account_id, 3, 2):
            self._add_owner_of(b, hop["dest"])
            if b.node_ids() >= {hop["source"], hop["dest"]}:
                props = self.get_node(hop["txn"]).properties
                if b.node(hop["txn"], "Transaction", f"₹{hop['amount']:,}", props):
                    b.edge(f"sent_{hop['txn']}", hop["source"], hop["txn"], "SENT", FACT)
                    b.edge(f"paid_{hop['txn']}", hop["txn"], hop["beneficiary"], "PAID", FACT)
        b.note_more(
            self._read(
                """
                MATCH (:Account {id: $id})-[:SENT]->(t:Transaction) RETURN count(t) AS n
                """,
                id=account_id,
            )[0]["n"]
            > 2
        )

    def _add_inflows(self, b: "_ViewBuilder", beneficiary_id: str) -> None:
        rows = self._read(
            """
            MATCH (:Beneficiary {id: $id})<-[:PAID]-(t:Transaction)
            WITH t ORDER BY t.timestamp DESC
            WITH collect(t.id) AS ids
            RETURN ids[0..8] AS shown, size(ids) AS total
            """,
            id=beneficiary_id,
        )
        if not rows:
            return
        for txn_id in rows[0]["shown"]:
            self._add_transaction(b, txn_id)
        b.note_more(rows[0]["total"] > len(rows[0]["shown"]))

    def _add_signals(self, b: "_ViewBuilder", beneficiary_id: str) -> None:
        rows = self._read(
            """
            MATCH (r:RiskSignal {beneficiaryId: $id})
            OPTIONAL MATCH (t:Transaction)-[f:FLAGGED_FOR]->(r)
            RETURN r.id AS id, r.code AS code, r.summary AS summary, r.provenance AS provenance,
                   collect({txn: t.id, edge: f.id, provenance: f.provenance})[0..6] AS flags
            ORDER BY r.id LIMIT 8
            """,
            id=beneficiary_id,
        )
        for r in rows:
            props = {"summary": r["summary"] or "", "provenance": r["provenance"] or ""}
            if not b.node(r["id"], "RiskSignal", r["code"] or r["id"], props):
                continue
            for f in r["flags"]:
                if f["txn"] and b.node_ids() >= {f["txn"]}:
                    b.edge(f["edge"], f["txn"], r["id"], "FLAGGED_FOR", f["provenance"])


class _ViewBuilder:
    def __init__(self, max_nodes: int, highlight: set[str]) -> None:
        self._max = max_nodes
        self._highlight = highlight
        self._nodes: dict[str, GraphNode] = {}
        self._edges: dict[str, GraphEdge] = {}
        self._truncated = False

    def node_ids(self) -> set[str]:
        return set(self._nodes)

    def note_more(self, more: bool) -> None:
        self._truncated = self._truncated or more

    def node(self, node_id: str, label: str, name: str, props: dict[str, Any]) -> bool:
        if node_id in self._nodes:
            return True
        if len(self._nodes) >= self._max:
            self._truncated = True
            return False
        clean = {k: _text(v) for k, v in props.items() if k != "id" and v is not None}
        self._nodes[node_id] = GraphNode(
            id=node_id,
            label=_label(label),
            name=name,
            highlighted=node_id in self._highlight,
            properties=clean,
        )
        return True

    def edge(
        self,
        edge_id: str,
        source: str,
        target: str,
        kind: str,
        provenance: str | None,
        edge_kind: str | None = None,
    ) -> None:
        if source not in self._nodes or target not in self._nodes or edge_id in self._edges:
            return
        self._edges[edge_id] = GraphEdge(
            id=edge_id,
            source=source,
            target=target,
            type=_edge_type(kind),
            provenance=_provenance(provenance),
            kind=edge_kind,
            highlighted=edge_id in self._highlight
            or (source in self._highlight and target in self._highlight),
        )

    def build(self) -> GraphView:
        return GraphView(
            nodes=list(self._nodes.values()),
            edges=list(self._edges.values()),
            truncated=self._truncated,
        )


def _label(value: str) -> NodeLabel:
    if value not in NODE_LABELS:
        raise ValueError(f"unexpected label {value}")
    return value  # type: ignore[return-value]


def _edge_type(value: str) -> EdgeType:
    if value not in REL_TYPES:
        raise ValueError(f"unexpected relationship {value}")
    return value  # type: ignore[return-value]


def build_graph_service(settings: Settings) -> GraphService:
    return GraphService(build_driver(settings))
