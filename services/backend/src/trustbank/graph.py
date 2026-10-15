"""Neo4j knowledge graph: schema, idempotent ingestion from the dataset, integrity checks."""

from collections.abc import Iterator, Mapping, Sequence
from datetime import datetime
from enum import Enum
from typing import Any

from neo4j import Driver, GraphDatabase
from pydantic import BaseModel

from trustbank.config import Settings
from trustbank.domain import Dataset, OwnerType

LABELS = ("Customer", "Account", "Transaction", "Beneficiary", "RiskSignal")
_BATCH = 500


def create_driver(settings: Settings) -> Driver:
    return GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password.get_secret_value()),
    )


def _props(model: BaseModel, *, exclude: set[str] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in model.model_dump(mode="python", exclude=exclude).items():
        if isinstance(value, Enum):
            value = value.value
        elif isinstance(value, datetime):
            # Firestore returns a datetime subclass the Neo4j driver rejects
            value = datetime.fromisoformat(value.isoformat())
        out[key] = value
    return out


def _chunks(rows: Sequence[Mapping[str, Any]], size: int) -> Iterator[list[Mapping[str, Any]]]:
    for i in range(0, len(rows), size):
        yield list(rows[i : i + size])


class GraphStore:
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def _run(self, query: str, **params: Any) -> list[dict[str, Any]]:
        records, _, _ = self._driver.execute_query(query, params)
        return [r.data() for r in records]

    def _write_batches(self, query: str, rows: Sequence[Mapping[str, Any]]) -> None:
        for chunk in _chunks(rows, _BATCH):
            self._run(query, rows=chunk)

    def apply_schema(self) -> None:
        for label in LABELS:
            self._run(
                f"CREATE CONSTRAINT {label.lower()}_id IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.id IS UNIQUE"
            )

    def reset(self) -> None:
        while self._run("MATCH (n) WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS c")[0]["c"]:
            pass

    def ingest(self, dataset: Dataset) -> None:
        """Idempotent MERGE of every node and relationship; safe to re-run."""
        self.apply_schema()
        self._write_batches(
            "UNWIND $rows AS r MERGE (n:Customer {id: r.id}) SET n += r",
            [_props(c) for c in dataset.customers],
        )
        self._write_batches(
            "UNWIND $rows AS r MERGE (n:Beneficiary {id: r.id}) SET n += r",
            [_props(b) for b in dataset.beneficiaries],
        )
        self._write_batches(
            "UNWIND $rows AS r MERGE (n:Account {id: r.id}) SET n += r",
            [_props(a) for a in dataset.accounts],
        )
        self._write_batches(
            "UNWIND $rows AS r MERGE (n:Transaction {id: r.id}) SET n += r",
            [
                _props(t, exclude={"source_account_id", "beneficiary_id"})
                for t in dataset.transactions
            ],
        )
        for owner_type, label in (
            (OwnerType.CUSTOMER, "Customer"),
            (OwnerType.BENEFICIARY, "Beneficiary"),
        ):
            self._write_batches(
                f"UNWIND $rows AS r MATCH (o:{label} {{id: r.owner}}), "
                "(a:Account {id: r.account}) "
                "MERGE (o)-[:OWNS]->(a)",
                [
                    {"owner": a.owner_id, "account": a.id}
                    for a in dataset.accounts
                    if a.owner_type == owner_type
                ],
            )
        pairs = [
            {"account": t.source_account_id, "txn": t.id, "ben": t.beneficiary_id}
            for t in dataset.transactions
        ]
        self._write_batches(
            "UNWIND $rows AS r MATCH (a:Account {id: r.account}), (t:Transaction {id: r.txn}) "
            "MERGE (a)-[:SENT]->(t)",
            pairs,
        )
        self._write_batches(
            "UNWIND $rows AS r MATCH (t:Transaction {id: r.txn}), (b:Beneficiary {id: r.ben}) "
            "MERGE (t)-[:PAID]->(b)",
            pairs,
        )
        self._write_batches(
            "UNWIND $rows AS r MATCH (a:Account {id: r.a}), (b:Account {id: r.b}) "
            "MERGE (a)-[c:CONNECTED_TO {id: r.id}]->(b) SET c.kind = r.kind, c.provenance = r.prov",
            [
                {
                    "id": c.id,
                    "a": c.account_a_id,
                    "b": c.account_b_id,
                    "kind": c.kind.value,
                    "prov": c.provenance.value,
                }
                for c in dataset.connections
            ],
        )

    def verify(self, dataset: Dataset) -> list[str]:
        """Return integrity problems (empty list means the graph matches the dataset)."""
        problems: list[str] = []
        expected_nodes = {
            "Customer": len(dataset.customers),
            "Beneficiary": len(dataset.beneficiaries),
            "Account": len(dataset.accounts),
            "Transaction": len(dataset.transactions),
        }
        for label, want in expected_nodes.items():
            got = self._run(f"MATCH (n:{label}) RETURN count(n) AS c")[0]["c"]
            if got != want:
                problems.append(f"{label}: expected {want} nodes, found {got}")
        expected_rels = {
            "OWNS": len(dataset.accounts),
            "SENT": len(dataset.transactions),
            "PAID": len(dataset.transactions),
            "CONNECTED_TO": len(dataset.connections),
        }
        for rel, want in expected_rels.items():
            got = self._run(f"MATCH ()-[r:{rel}]->() RETURN count(r) AS c")[0]["c"]
            if got != want:
                problems.append(f"{rel}: expected {want} relationships, found {got}")
        bad_txn = self._run(
            "MATCH (t:Transaction) "
            "WHERE COUNT { (:Account)-[:SENT]->(t) } <> 1 "
            "OR COUNT { (t)-[:PAID]->(:Beneficiary) } <> 1 "
            "RETURN t.id AS id LIMIT 5"
        )
        problems += [f"Transaction {r['id']}: needs exactly one SENT and one PAID" for r in bad_txn]
        no_owner = self._run(
            "MATCH (a:Account) WHERE COUNT { ()-[:OWNS]->(a) } <> 1 RETURN a.id AS id LIMIT 5"
        )
        problems += [f"Account {r['id']}: needs exactly one owner" for r in no_owner]
        return problems
