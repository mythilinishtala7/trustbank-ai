import json
import socket
import threading
import time
from typing import Any

import httpx
import pytest
import uvicorn

from tests.conftest import INVESTIGATOR_CODE, Harness
from tests.support import StubGraph, StubOrchestrator
from tests.test_api_auth import assert_error
from tests.test_api_payments import NOVA, RAHUL, SCAM
from trustbank.config import Settings
from trustbank.main import create_app
from trustbank.store import DatasetRepository


def inv_get(h: Harness, path: str, **kw: Any) -> Any:
    return h.client.get(f"/api/v1/investigation{path}", headers=h.investigator(), **kw)


def hold_payment(h: Harness) -> str:
    headers = h.login()
    pid = str(h.pay(headers, NOVA, 25000)["id"])
    h.act(headers, pid, "answers", {"answers": SCAM})
    return pid


def test_list_recent_newest_first(harness: Harness) -> None:
    harness.clock.advance(3 * 86400)
    headers = harness.login()
    harness.pay(headers, RAHUL, 10)
    harness.clock.advance(5)
    newest = str(harness.pay(headers, RAHUL, 20)["id"])
    res = inv_get(harness, "/transactions", params={"limit": 5})
    assert res.status_code == 200
    items = res.json()
    assert items[0]["transactionId"] == newest and len(items) <= 5
    assert set(items[0]) == {
        "transactionId", "customerName", "recipientName", "amount", "status", "createdAt",
    }  # fmt: skip
    assert_error(inv_get(harness, "/transactions", params={"limit": 0}), 422, "VALIDATION_ERROR")


def test_detail_payment_has_assessments_graph_and_audit(harness: Harness) -> None:
    pid = hold_payment(harness)
    res = inv_get(harness, f"/transactions/{pid}")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "PAYMENT" and body["transactionId"] == pid and body["simulated"] is True
    assert (
        body["summary"]["status"] == "HOLD_ACTIVE"
        and body["summary"]["customerName"] == "Asha Menon"
    )
    stages = [a["stage"] for a in body["assessments"]]
    assert stages == ["INITIAL", "FINAL"]
    initial, final = body["assessments"]
    assert initial["aggregate"]["elevated"] is True and initial["aggregate"]["action"] == "REVIEW"
    assert final["aggregate"]["action"] == "HOLD" and final["aggregate"]["contextPoints"] == 25
    assert final["model"] == "stub-model" and final["complete"] is True
    assert final["config"]["holdSeconds"] == 180
    assert final["answers"] and final["questions"] and final["explanation"]
    assert initial["toolCalls"][0]["tool"] == "flow_profile"
    assert {"nodes", "edges", "truncated"} == set(body["graph"])
    call = harness.graph.graph_calls[-1]
    assert call["beneficiary_id"] == "ben_novatrade" and call["customer_id"] == "cust_asha"
    assert {"acct_novatrade", "txn_net_in_1"} <= call["highlight_ids"]  # type: ignore[operator]
    audits = [d.to_dict() for d in harness.dataset.client.collection("audit_log").stream()]
    assert any(
        a and a.get("action") == "INVESTIGATION_LOOKUP" and a.get("transaction_id") == pid
        for a in audits
    )


def test_assessments_are_immutable(harness: Harness) -> None:
    pid = hold_payment(harness)
    coll = harness.dataset.client.collection("assessments")
    docs = list(coll.where("payment_id", "==", pid).stream()) or [
        d for d in coll.stream() if (d.to_dict() or {}).get("paymentId") == pid
    ]
    assert len(docs) == 2
    from google.api_core.exceptions import AlreadyExists

    with pytest.raises(AlreadyExists):
        coll.document(docs[0].id).create({"x": 1})


def test_detail_historical_and_404(harness: Harness) -> None:
    res = inv_get(harness, "/transactions/txn_hist_1")
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "HISTORICAL" and body["assessments"] == []
    assert_error(inv_get(harness, "/transactions/txn_nope1234"), 404, "NOT_FOUND")
    assert_error(inv_get(harness, "/transactions/not%20valid!"), 404, "NOT_FOUND")


def test_graph_failure_degrades_instead_of_500(harness: Harness) -> None:
    def boom(**_: Any) -> Any:
        raise ConnectionError("neo4j down")

    harness.graph.investigation_graph = boom  # type: ignore[method-assign]
    res = inv_get(harness, "/transactions/txn_hist_1")
    assert res.status_code == 200 and res.json()["graph"]["nodes"] == []


def test_timeline_persisted_without_any_subscriber(harness: Harness) -> None:
    pid = hold_payment(harness)
    res = inv_get(harness, f"/transactions/{pid}/timeline")
    assert res.status_code == 200
    body = res.json()
    seqs = [e["seq"] for e in body["events"]]
    assert seqs == list(range(1, len(seqs) + 1)) and len(seqs) >= 6
    assert body["paymentStatus"] == "HOLD_ACTIVE" and body["done"] is True
    agents = [e["agentId"] for e in body["events"]]
    assert {"anomaly", "fraud_network", "questionnaire", "explainer", "policy"} <= set(agents)
    assert any(e["type"] == "STATE_CHANGE" for e in body["events"])
    assert set(body["events"][0]) == {
        "seq", "at", "agentId", "type", "status", "durationMs", "tool", "parameters",
        "resultSummary", "message",
    }  # fmt: skip
    after = inv_get(harness, f"/transactions/{pid}/timeline", params={"after": seqs[2]}).json()
    assert [e["seq"] for e in after["events"]] == seqs[3:]


def parse_sse(raw: str) -> list[dict[str, str]]:
    frames = []
    for block in raw.strip().split("\n\n"):
        frame: dict[str, str] = {}
        for line in block.splitlines():
            if line.startswith(":"):
                frame.setdefault("comment", line)
            elif ": " in line:
                k, v = line.split(": ", 1)
                frame[k] = v
        frames.append(frame)
    return frames


def test_sse_replays_in_order_then_done(harness: Harness) -> None:
    pid = hold_payment(harness)
    headers = harness.investigator()
    with harness.client.stream(
        "GET", f"/api/v1/investigation/transactions/{pid}/events", headers=headers
    ) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        raw = "".join(res.iter_text())
    frames = parse_sse(raw)
    timeline = [f for f in frames if f.get("event") == "timeline"]
    ids = [int(f["id"]) for f in timeline]
    assert ids == sorted(ids) == list(range(1, len(ids) + 1))
    for f in timeline:
        data = json.loads(f["data"])
        assert data["seq"] == int(f["id"])
    assert frames[-1].get("event") == "done"

    with harness.client.stream(
        "GET",
        f"/api/v1/investigation/transactions/{pid}/events",
        params={"after": ids[-2]},
        headers=headers,
    ) as res:
        resumed = parse_sse("".join(res.iter_text()))
    assert [int(f["id"]) for f in resumed if f.get("event") == "timeline"] == [ids[-1]]


def test_sse_auth_and_404(harness: Harness) -> None:
    assert_error(
        harness.client.get(
            "/api/v1/investigation/transactions/txn_nope1234/events", headers=harness.investigator()
        ),
        404,
        "NOT_FOUND",
    )


def test_sse_streams_live_events_and_pings(settings: Settings, dataset: DatasetRepository) -> None:
    # TestClient buffers streamed bodies, so use a real server for the live case.
    orchestrator, graph = StubOrchestrator(), StubGraph()
    orchestrator.gate = threading.Event()
    app = create_app(
        settings,
        orchestrator=orchestrator,
        graph=graph,  # type: ignore[arg-type]
        repo=dataset,
        sse_ping_interval=0.2,
        sse_poll_interval=0.05,
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()
    base = f"http://127.0.0.1:{port}/api/v1"
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    frames: list[str] = []
    result: dict[str, Any] = {}
    try:
        with httpx.Client(base_url=base, timeout=15) as client:
            token = client.post("/auth/customer", json={"personaId": "cust_asha"}).json()["token"]
            inv = client.post("/auth/investigator", json={"code": INVESTIGATOR_CODE}).json()[
                "token"
            ]

            def create() -> None:
                result["pay"] = client.post(
                    "/payments",
                    headers={"Authorization": f"Bearer {token}", "Idempotency-Key": "live-sse-1"},
                    json={"recipient": RAHUL, "amount": 10},
                ).json()

            creator = threading.Thread(target=create)
            creator.start()
            for _ in range(200):
                if orchestrator.detector_calls:
                    break
                time.sleep(0.05)
            pid = orchestrator.detector_calls[0]

            def consume() -> None:
                with httpx.Client(base_url=base, timeout=15) as reader_client:
                    url = f"/investigation/transactions/{pid}/events"
                    with reader_client.stream(
                        "GET", url, headers={"Authorization": f"Bearer {inv}"}
                    ) as res:
                        for chunk in res.iter_text():
                            frames.append(chunk)

            reader = threading.Thread(target=consume)
            reader.start()
            time.sleep(1.0)
            live = "".join(frames)
            orchestrator.gate.set()
            creator.join(10)
            reader.join(10)
            assert "event: timeline" in live and ": ping" in live and "event: done" not in live
            assert not reader.is_alive()
    finally:
        orchestrator.gate.set()
        server.should_exit = True
        server_thread.join(5)
    text = "".join(frames)
    assert text.count("event: done") == 1
    assert result["pay"]["status"] == "READY_FOR_AUTH"
    seqs = [int(line.split(": ")[1]) for line in text.splitlines() if line.startswith("id: ")]
    assert seqs == list(range(1, len(seqs) + 1)) and len(seqs) >= 5
