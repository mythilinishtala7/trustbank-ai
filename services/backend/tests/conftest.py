import socket
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.support import NOW, FixedClock, StubGraph, StubOrchestrator
from trustbank.config import Settings
from trustbank.fixtures import build_dataset
from trustbank.main import create_app
from trustbank.store import DatasetRepository, create_client

EMULATOR = "127.0.0.1:8085"
INVESTIGATOR_CODE = "open-sesame-test"
PIN = "482917"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="session")
def settings() -> Settings:
    host, port = EMULATOR.split(":")
    try:
        socket.create_connection((host, int(port)), timeout=1).close()
    except OSError:
        pytest.skip(f"Firestore emulator not running on {EMULATOR}")
    return Settings(
        _env_file=None,
        environment="test",
        google_cloud_project=f"trustbank-test-{uuid.uuid4().hex[:10]}",
        firestore_emulator_host=EMULATOR,
        investigator_code=INVESTIGATOR_CODE,
        token_secret="x" * 40,
    )


@pytest.fixture(scope="session")
def dataset(settings: Settings) -> DatasetRepository:
    repo = DatasetRepository(create_client(settings))
    repo.seed(build_dataset(NOW))
    return repo


class Harness:
    def __init__(
        self,
        client: TestClient,
        orchestrator: StubOrchestrator,
        graph: StubGraph,
        clock: FixedClock,
        dataset: DatasetRepository,
    ) -> None:
        self.client = client
        self.orchestrator = orchestrator
        self.graph = graph
        self.clock = clock
        self.dataset = dataset
        self._keys = 0

    def login(self, persona: str = "cust_asha") -> dict[str, str]:
        res = self.client.post("/api/v1/auth/customer", json={"personaId": persona})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['token']}"}

    def investigator(self) -> dict[str, str]:
        res = self.client.post("/api/v1/auth/investigator", json={"code": INVESTIGATOR_CODE})
        assert res.status_code == 200, res.text
        return {"Authorization": f"Bearer {res.json()['token']}"}

    def pay(
        self,
        headers: dict[str, str],
        recipient: str,
        amount: int = 500,
        key: str | None = None,
        note: str = "",
    ) -> dict[str, object]:
        self._keys += 1
        res = self.client.post(
            "/api/v1/payments",
            headers={**headers, "Idempotency-Key": key or f"key-{uuid.uuid4().hex}"},
            json={"recipient": recipient, "amount": amount, "note": note},
        )
        assert res.status_code == 200, res.text
        body: dict[str, object] = res.json()
        return body

    def act(
        self, headers: dict[str, str], payment_id: str, action: str, json: object | None = None
    ) -> object:
        return self.client.post(
            f"/api/v1/payments/{payment_id}/{action}", headers=headers, json=json or {}
        )


@pytest.fixture
def harness(settings: Settings, dataset: DatasetRepository) -> Iterator[Harness]:
    orchestrator, graph, clock = StubOrchestrator(), StubGraph(), FixedClock()
    app = create_app(
        settings,
        orchestrator=orchestrator,
        graph=graph,  # type: ignore[arg-type]
        repo=dataset,
        clock=clock,
        sse_ping_interval=0.2,
        sse_poll_interval=0.05,
    )
    with TestClient(app) as client:
        yield Harness(client, orchestrator, graph, clock, dataset)
