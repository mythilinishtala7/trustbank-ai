"""Shared Neo4j-backed fixtures. The graph is rebuilt from the deterministic dataset."""

import socket
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from trustbank.config import Settings
from trustbank.domain import Dataset
from trustbank.fixtures import build_dataset
from trustbank.graph import GraphService
from trustbank.graph.common import build_driver
from trustbank.graph.ingest import ensure_constraints, ingest_dataset, reset_graph

NOW = datetime.now(UTC).replace(second=0, microsecond=0)


class MemoryHistory:
    """The history reads the anomaly agent needs, served from the in-memory dataset."""

    def __init__(self, dataset: Dataset) -> None:
        self._d = dataset

    def get_customer(self, customer_id: str) -> Any:
        return next((c for c in self._d.customers if c.id == customer_id), None)

    def get_beneficiary(self, beneficiary_id: str) -> Any:
        return next((b for b in self._d.beneficiaries if b.id == beneficiary_id), None)

    def account_for_owner(self, owner_id: str) -> Any:
        return next((a for a in self._d.accounts if a.owner_id == owner_id), None)

    def transactions_from_account(self, account_id: str, limit: int = 200) -> list[Any]:
        rows = [t for t in self._d.transactions if t.source_account_id == account_id]
        return sorted(rows, key=lambda t: t.timestamp, reverse=True)[:limit]


@dataclass
class GraphEnv:
    settings: Settings
    dataset: Dataset
    graph: GraphService
    history: MemoryHistory

    def rebuild(self, dataset: Dataset | None = None) -> None:
        reset_graph(self.graph._driver)
        ingest_dataset(self.graph._driver, dataset or self.dataset)


@pytest.fixture(scope="session")
def graph_env() -> Iterator[GraphEnv]:
    settings = Settings(_env_file=None, environment="test")
    host, port = settings.neo4j_uri.removeprefix("bolt://").split(":")
    try:
        socket.create_connection((host, int(port)), timeout=1).close()
    except OSError:
        pytest.skip(f"Neo4j not running on {settings.neo4j_uri}")
    driver = build_driver(settings)
    graph = GraphService(driver)
    dataset = build_dataset(NOW)
    ensure_constraints(driver)
    env = GraphEnv(settings, dataset, graph, MemoryHistory(dataset))
    env.rebuild()
    yield env
    graph.close()
