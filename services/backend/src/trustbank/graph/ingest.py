"""Neo4j ingestion: python -m trustbank.graph.ingest [--reset]

Projects the Firestore dataset into the knowledge graph with idempotent MERGE.
Only facts are written; no verdicts, scores or RiskSignal nodes.
"""

import argparse
from typing import Any

from neo4j import Driver

from trustbank.config import get_settings
from trustbank.domain import Dataset, OwnerType
from trustbank.graph.common import FACT, build_driver, plain_datetime
from trustbank.graph.schema import CONSTRAINTS, NODE_LABELS
from trustbank.store import DatasetRepository, create_client

_BATCH = 500

_UPSERTS: dict[str, str] = {
    "customers": """
        UNWIND $rows AS r MERGE (n:Customer {id: r.id})
        SET n.name = r.name, n.handle = r.handle, n.isDemoPersona = r.persona""",
    "beneficiaries": """
        UNWIND $rows AS r MERGE (n:Beneficiary {id: r.id})
        SET n.name = r.name, n.handle = r.handle, n.firstSeenAt = r.firstSeenAt""",
    "accounts": """
        UNWIND $rows AS r MERGE (n:Account {id: r.id})
        SET n.openedAt = r.openedAt, n.maskedNumber = r.maskedNumber, n.ownerType = r.ownerType""",
    "transactions": """
        UNWIND $rows AS r MERGE (n:Transaction {id: r.id})
        SET n.amount = r.amount, n.currency = r.currency, n.note = r.note,
            n.timestamp = r.timestamp, n.status = r.status""",
    "owns_customer": """
        UNWIND $rows AS r MATCH (o:Customer {id: r.owner}), (a:Account {id: r.account})
        MERGE (o)-[rel:OWNS {id: r.id}]->(a) SET rel.provenance = $fact""",
    "owns_beneficiary": """
        UNWIND $rows AS r MATCH (o:Beneficiary {id: r.owner}), (a:Account {id: r.account})
        MERGE (o)-[rel:OWNS {id: r.id}]->(a) SET rel.provenance = $fact""",
    "sent": """
        UNWIND $rows AS r MATCH (a:Account {id: r.account}), (t:Transaction {id: r.txn})
        MERGE (a)-[rel:SENT {id: r.id}]->(t) SET rel.provenance = $fact""",
    "paid": """
        UNWIND $rows AS r MATCH (t:Transaction {id: r.txn}), (b:Beneficiary {id: r.beneficiary})
        MERGE (t)-[rel:PAID {id: r.id}]->(b) SET rel.provenance = $fact""",
    "connected": """
        UNWIND $rows AS r MATCH (a:Account {id: r.a}), (b:Account {id: r.b})
        MERGE (a)-[rel:CONNECTED_TO {id: r.id}]->(b)
        SET rel.kind = r.kind, rel.provenance = r.provenance""",
}


def ensure_constraints(driver: Driver) -> None:
    for statement in CONSTRAINTS:
        driver.execute_query(statement)


def reset_graph(driver: Driver) -> None:
    """Delete every node of the graph schema (the graph is a projection; Firestore is the truth)."""
    while True:
        records, _, _ = driver.execute_query(
            """
            MATCH (n) WHERE any(l IN labels(n) WHERE l IN $labels)
            WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS deleted
            """,
            labels=list(NODE_LABELS),
        )
        if records[0]["deleted"] == 0:
            return


def _chunks(rows: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    return [rows[i : i + _BATCH] for i in range(0, len(rows), _BATCH)]


def dataset_rows(dataset: Dataset) -> dict[str, list[dict[str, Any]]]:
    owners_c = [a for a in dataset.accounts if a.owner_type is OwnerType.CUSTOMER]
    owners_b = [a for a in dataset.accounts if a.owner_type is OwnerType.BENEFICIARY]
    return {
        "customers": [
            {"id": c.id, "name": c.display_name, "handle": c.handle, "persona": c.is_demo_persona}
            for c in dataset.customers
        ],
        "beneficiaries": [
            {
                "id": b.id,
                "name": b.display_name,
                "handle": b.handle,
                "firstSeenAt": plain_datetime(b.first_seen_at),
            }
            for b in dataset.beneficiaries
        ],
        "accounts": [
            {
                "id": a.id,
                "openedAt": plain_datetime(a.opened_at),
                "maskedNumber": a.masked_number,
                "ownerType": a.owner_type.value,
            }
            for a in dataset.accounts
        ],
        "transactions": [
            {
                "id": t.id,
                "amount": t.amount,
                "currency": t.currency,
                "note": t.note,
                "timestamp": plain_datetime(t.timestamp),
                "status": t.status.value,
            }
            for t in dataset.transactions
        ],
        "owns_customer": [
            {"id": f"own_{a.id}", "owner": a.owner_id, "account": a.id} for a in owners_c
        ],
        "owns_beneficiary": [
            {"id": f"own_{a.id}", "owner": a.owner_id, "account": a.id} for a in owners_b
        ],
        "sent": [
            {"id": f"sent_{t.id}", "account": t.source_account_id, "txn": t.id}
            for t in dataset.transactions
        ],
        "paid": [
            {"id": f"paid_{t.id}", "txn": t.id, "beneficiary": t.beneficiary_id}
            for t in dataset.transactions
        ],
        "connected": [
            {
                "id": c.id,
                "a": c.account_a_id,
                "b": c.account_b_id,
                "kind": c.kind.value,
                "provenance": c.provenance.value,
            }
            for c in dataset.connections
        ],
    }


def ingest_dataset(driver: Driver, dataset: Dataset) -> dict[str, int]:
    """Constraints first, then MERGE nodes, then relationships. Safe to run repeatedly."""
    ensure_constraints(driver)
    counts: dict[str, int] = {}
    for name, rows in dataset_rows(dataset).items():
        for chunk in _chunks(rows):
            driver.execute_query(_UPSERTS[name], rows=chunk, fact=FACT)
        counts[name] = len(rows)
    return counts


def check_integrity(driver: Driver, dataset: Dataset | None = None) -> list[str]:
    """Return human-readable violations (empty when the graph satisfies the spec)."""
    problems: list[str] = []

    def scalar(query: str, **params: Any) -> int:
        records, _, _ = driver.execute_query(query, **params)
        return int(records[0][0])

    bad_sent = scalar(
        "MATCH (t:Transaction) WHERE COUNT { (:Account)-[:SENT]->(t) } <> 1 RETURN count(t)"
    )
    bad_paid = scalar(
        "MATCH (t:Transaction) WHERE COUNT { (t)-[:PAID]->(:Beneficiary) } <> 1 RETURN count(t)"
    )
    bad_owner = scalar(
        """MATCH (a:Account)
        WHERE COUNT { (:Customer|Beneficiary)-[:OWNS]->(a) } <> 1 RETURN count(a)"""
    )
    no_provenance = scalar(
        """MATCH ()-[r]->() WHERE type(r) IN ['CONNECTED_TO', 'FLAGGED_FOR']
        AND (r.provenance IS NULL OR r.id IS NULL) RETURN count(r)"""
    )
    for count, message in (
        (bad_sent, "transactions without exactly one SENT"),
        (bad_paid, "transactions without exactly one PAID"),
        (bad_owner, "accounts without exactly one owner"),
        (no_provenance, "CONNECTED_TO/FLAGGED_FOR without provenance or id"),
    ):
        if count:
            problems.append(f"{count} {message}")

    if dataset is not None:
        for label, ids in (
            ("Customer", [c.id for c in dataset.customers]),
            ("Beneficiary", [b.id for b in dataset.beneficiaries]),
            ("Account", [a.id for a in dataset.accounts]),
            ("Transaction", [t.id for t in dataset.transactions]),
        ):
            records, _, _ = driver.execute_query(
                f"MATCH (n:{label}) WHERE n.id IN $ids RETURN count(n) AS c", ids=ids
            )
            if records[0]["c"] != len(ids):
                problems.append(f"{label}: {len(ids) - records[0]['c']} dataset ids missing")
    return problems


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Ingest the Firestore dataset into Neo4j.")
    parser.add_argument("--reset", action="store_true", help="clear the graph first")
    args = parser.parse_args(argv)

    settings = get_settings()
    dataset = DatasetRepository(create_client(settings)).load()
    driver = build_driver(settings)
    try:
        if args.reset:
            reset_graph(driver)
            print("reset: graph cleared")
        for name, n in ingest_dataset(driver, dataset).items():
            print(f"{name}: {n}")
        problems = check_integrity(driver, dataset)
    finally:
        driver.close()
    if problems:
        raise SystemExit("integrity check failed: " + "; ".join(problems))
    print("integrity: ok")


if __name__ == "__main__":
    main()
