from tests.conftest import Harness
from tests.test_api_auth import assert_error


def test_request_id_generated_and_echoed(harness: Harness) -> None:
    res = harness.client.get("/api/v1/health")
    assert res.headers["X-Request-Id"]
    res = harness.client.get("/api/v1/health", headers={"X-Request-Id": "req-abc-12345"})
    assert res.headers["X-Request-Id"] == "req-abc-12345"


def test_unknown_route_is_404_error_format(harness: Harness) -> None:
    assert_error(harness.client.get("/api/v1/nope"), 404, "NOT_FOUND")


def test_validation_error_is_422_and_does_not_echo_input(harness: Harness) -> None:
    headers = harness.login()
    res = harness.client.post(
        "/api/v1/payments/txn_00000000/authorize", headers=headers, json={"pin": "12ab"}
    )
    err = assert_error(res, 422, "VALIDATION_ERROR")
    assert "12ab" not in res.text
    assert "Traceback" not in err["message"]


def test_bad_lookup_query(harness: Harness) -> None:
    headers = harness.login()
    for q in ("hello", "12345", "1" * 19, "no spaces@bank"):
        assert_error(
            harness.client.get("/api/v1/recipients/lookup", params={"q": q}, headers=headers),
            422,
            "VALIDATION_ERROR",
        )


def test_payment_requires_idempotency_key(harness: Harness) -> None:
    res = harness.client.post(
        "/api/v1/payments",
        headers=harness.login(),
        json={"recipient": "rahul.verma@trustpay", "amount": 100},
    )
    assert_error(res, 422, "VALIDATION_ERROR")


def test_payment_body_validation(harness: Harness) -> None:
    headers = {**harness.login(), "Idempotency-Key": "k-validation"}
    for body in (
        {"recipient": "rahul.verma@trustpay", "amount": 0},
        {"recipient": "rahul.verma@trustpay", "amount": -5},
        {"recipient": "rahul.verma@trustpay", "amount": 10.5},
        {"recipient": "rahul.verma@trustpay", "amount": 10, "note": "x" * 81},
        {"recipient": "garbage", "amount": 10},
        {"amount": 10},
    ):
        assert_error(
            harness.client.post("/api/v1/payments", headers=headers, json=body),
            422,
            "VALIDATION_ERROR",
        )


def test_health_ok_and_degraded(harness: Harness) -> None:
    res = harness.client.get("/api/v1/health")
    assert res.status_code == 200
    assert res.json() == {
        "status": "ok",
        "checks": {"firestore": "ok", "neo4j": "ok", "model": "unchecked"},
    }
    harness.graph.up = False
    res = harness.client.get("/api/v1/health")
    assert res.json()["status"] == "degraded" and res.json()["checks"]["neo4j"] == "down"
