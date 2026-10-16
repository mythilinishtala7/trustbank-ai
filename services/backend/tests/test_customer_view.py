import json
import logging
from typing import Any

import pytest

from tests.conftest import PIN, Harness
from tests.test_api_payments import BENIGN, NOVA, RAHUL, SCAM

ALLOWED = {
    "id", "status", "recipient", "amount", "note", "createdAt", "serverTime", "explanation",
    "reasons", "questions", "holdUntil", "verified", "actions", "simulated",
}  # fmt: skip
ALLOWED_NESTED = {
    "recipient": {"displayName", "handle", "verified"},
    "questions": {"id", "text", "options", "allowFreeText"},
    "options": {"value", "label"},
}
FORBIDDEN = [
    "anomaly", "fraud_network", "fraudnetwork", "network.", "score", "toolcall", "graph",
    "threshold", "evidence", "agent", "preScore", "confidence", "context.", "Priya Nair",
    "cust_priya", "acct_", "ben_", "RiskSignal", "provenance", "tool_calls", "signal",
]  # fmt: skip


def walk(value: Any, path: str = "") -> None:
    if isinstance(value, dict):
        key = path.rsplit(".", 1)[-1]
        nested = ALLOWED_NESTED.get(key)
        if path == "":
            assert set(value) <= ALLOWED, set(value) - ALLOWED
        elif nested is not None:
            assert set(value) <= nested, (path, set(value) - nested)
        for k, v in value.items():
            walk(v, f"{path}.{k}" if path else k)
    elif isinstance(value, list):
        for item in value:
            walk(item, path)


def assert_clean(body: dict[str, Any]) -> None:
    walk(body)
    text = json.dumps(body).lower()
    for word in FORBIDDEN:
        assert word.lower() not in text, word


def test_customer_payment_whitelist_across_flow(harness: Harness) -> None:
    headers = harness.login()
    low = harness.pay(headers, RAHUL, 100)
    assert_clean(low)
    pay = harness.pay(headers, NOVA, 25000)
    assert pay["status"] == "QUESTIONNAIRE"
    assert_clean(pay)
    pid = str(pay["id"])
    hold = harness.act(headers, pid, "answers", {"answers": SCAM}).json()  # type: ignore[attr-defined]
    assert hold["status"] == "HOLD_ACTIVE"
    assert_clean(hold)
    assert_clean(harness.client.get(f"/api/v1/payments/{pid}", headers=headers).json())
    harness.clock.advance(200)
    expired = harness.client.get(f"/api/v1/payments/{pid}", headers=headers).json()
    assert expired["status"] == "HOLD_EXPIRED"
    assert_clean(expired)
    harness.act(headers, pid, "cancel")
    review = harness.act(headers, str(harness.pay(headers, NOVA, 25000)["id"]), "cancel").json()  # type: ignore[attr-defined]
    assert_clean(review)


def test_review_and_incomplete_views_are_clean(harness: Harness) -> None:
    headers = harness.login()
    pid = str(harness.pay(headers, NOVA, 25000)["id"])
    review = harness.act(headers, pid, "answers", {"answers": BENIGN}).json()  # type: ignore[attr-defined]
    assert review["status"] == "REVIEW"
    assert_clean(review)
    harness.orchestrator.failed_detector_for.add("ben_rahul")
    assert_clean(harness.pay(headers, RAHUL, 100))


def test_me_response_is_clean(harness: Harness) -> None:
    res = harness.client.get("/api/v1/me", headers=harness.login()).json()
    text = json.dumps(res)
    assert "Priya Nair" not in text and "cust_" not in text and "acct_" not in text


def test_whitelist_walker_catches_leaks() -> None:
    with pytest.raises(AssertionError):
        assert_clean({"id": "txn_1", "riskScore": 80})
    with pytest.raises(AssertionError):
        assert_clean({"id": "txn_1", "explanation": "flagged by the fraud_network agent"})
    with pytest.raises(AssertionError):
        assert_clean({"id": "txn_1", "recipient": {"handle": "a@b", "internalId": "ben_x"}})


def test_pin_never_in_logs_or_storage(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    headers = harness.login()
    pid = str(harness.pay(headers, RAHUL, 55)["id"])
    bad = harness.act(headers, pid, "authorize", {"pin": "12"})
    assert bad.status_code == 422  # type: ignore[attr-defined]
    ok = harness.act(headers, pid, "authorize", {"pin": PIN})
    assert ok.status_code == 200  # type: ignore[attr-defined]
    assert PIN not in ok.text  # type: ignore[attr-defined]
    logs = caplog.text + "".join(json.dumps(r.__dict__, default=str) for r in caplog.records)
    assert PIN not in logs and "482917" not in logs

    db = harness.dataset.client
    dumps: list[str] = []
    for name in ("payments", "assessments", "audit_log", "idempotency_keys", "transactions"):
        for snap in db.collection(name).stream():
            dumps.append(json.dumps(snap.to_dict(), default=str))
            if name == "payments":
                dumps += [
                    json.dumps(e.to_dict(), default=str)
                    for e in snap.reference.collection("events").stream()
                ]
    assert dumps and not any(PIN in d for d in dumps)


def test_persisted_payment_holds_server_side_data(harness: Harness) -> None:
    headers = harness.login()
    pid = str(harness.pay(headers, NOVA, 25000)["id"])
    snap = harness.dataset.client.collection("payments").document(pid).get().to_dict()
    assert snap is not None
    text = json.dumps(snap, default=str)
    assert "pre_score" in text or "preScore" in text
