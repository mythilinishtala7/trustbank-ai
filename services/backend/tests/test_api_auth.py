import json
import logging
from datetime import timedelta

import pytest

from tests.conftest import INVESTIGATOR_CODE, Harness

CUSTOMER_ROUTES = [
    ("get", "/api/v1/me"),
    ("get", "/api/v1/recipients/lookup?q=rahul.verma@trustpay"),
    ("get", "/api/v1/payments/txn_00000000"),
    ("post", "/api/v1/payments/txn_00000000/cancel"),
]
INVESTIGATOR_ROUTES = [
    ("get", "/api/v1/investigation/transactions"),
    ("get", "/api/v1/investigation/transactions/txn_hist_1"),
    ("get", "/api/v1/investigation/transactions/txn_hist_1/timeline"),
    ("get", "/api/v1/investigation/transactions/txn_hist_1/events"),
]


def assert_error(res: object, status: int, code: str) -> dict[str, str]:
    assert res.status_code == status, res.text  # type: ignore[attr-defined]
    body = res.json()  # type: ignore[attr-defined]
    assert set(body) == {"error"}
    err: dict[str, str] = body["error"]
    assert set(err) == {"code", "message", "requestId"}
    assert err["code"] == code
    assert err["requestId"] == res.headers["X-Request-Id"]  # type: ignore[attr-defined]
    return err


def test_personas(harness: Harness) -> None:
    res = harness.client.get("/api/v1/personas")
    assert res.status_code == 200
    ids = {p["id"] for p in res.json()}
    assert ids == {"cust_asha", "cust_priya"}
    assert set(res.json()[0]) == {"id", "displayName", "handle", "blurb"}


def test_customer_login_and_me(harness: Harness) -> None:
    res = harness.client.post("/api/v1/auth/customer", json={"personaId": "cust_asha"})
    body = res.json()
    assert body["role"] == "customer" and body["displayName"] == "Asha Menon"
    assert set(body) == {"token", "role", "expiresAt", "displayName"}
    me = harness.client.get("/api/v1/me", headers=harness.login())
    assert me.status_code == 200
    assert set(me.json()) == {"displayName", "handle", "balance", "recentTransactions"}
    assert len(me.json()["recentTransactions"]) <= 5


def test_unknown_persona_rejected(harness: Harness) -> None:
    res = harness.client.post("/api/v1/auth/customer", json={"personaId": "cust_nobody"})
    assert res.status_code in (401, 404, 422)
    assert "error" in res.json()


@pytest.mark.parametrize(("method", "path"), CUSTOMER_ROUTES)
def test_customer_routes_need_token(harness: Harness, method: str, path: str) -> None:
    assert_error(getattr(harness.client, method)(path), 401, "UNAUTHENTICATED")
    bad = {"Authorization": "Bearer nonsense"}
    assert_error(getattr(harness.client, method)(path, headers=bad), 401, "UNAUTHENTICATED")
    assert_error(
        getattr(harness.client, method)(path, headers=harness.investigator()), 403, "FORBIDDEN"
    )


@pytest.mark.parametrize(("method", "path"), INVESTIGATOR_ROUTES)
def test_investigator_routes_need_investigator(harness: Harness, method: str, path: str) -> None:
    assert_error(getattr(harness.client, method)(path), 401, "UNAUTHENTICATED")
    assert_error(getattr(harness.client, method)(path, headers=harness.login()), 403, "FORBIDDEN")


def test_expired_and_tampered_tokens(harness: Harness) -> None:
    headers = harness.login()
    token = headers["Authorization"].split()[1]
    tampered = {"Authorization": f"Bearer {token[:-2]}xx"}
    assert_error(harness.client.get("/api/v1/me", headers=tampered), 401, "UNAUTHENTICATED")
    harness.clock.advance(8 * 3600 + 1)
    assert_error(harness.client.get("/api/v1/me", headers=headers), 401, "UNAUTHENTICATED")


def test_token_carries_role_subject_expiry(harness: Harness) -> None:
    from trustbank.auth import TokenService

    token = harness.login()["Authorization"].split()[1]
    principal = TokenService("x" * 40, timedelta(hours=8), harness.clock).verify(token)
    assert principal.role == "customer" and principal.subject == "cust_asha"


def test_investigator_wrong_code_is_generic_and_rate_limited(harness: Harness) -> None:
    for _ in range(5):
        err = assert_error(
            harness.client.post("/api/v1/auth/investigator", json={"code": "wrong"}),
            401,
            "UNAUTHENTICATED",
        )
        assert "code" not in err["message"].lower() or "invalid" in err["message"].lower()
    assert_error(
        harness.client.post("/api/v1/auth/investigator", json={"code": "wrong"}),
        429,
        "RATE_LIMITED",
    )


def test_investigator_login_ok(harness: Harness) -> None:
    res = harness.client.post("/api/v1/auth/investigator", json={"code": INVESTIGATOR_CODE})
    assert res.status_code == 200
    assert (
        set(res.json()) == {"token", "role", "expiresAt"} and res.json()["role"] == "investigator"
    )


def test_secrets_never_logged(harness: Harness, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    harness.client.post("/api/v1/auth/investigator", json={"code": "guess-guess-guess"})
    headers = harness.investigator()
    harness.client.get("/api/v1/investigation/transactions", headers=headers)
    text = caplog.text + "".join(json.dumps(r.__dict__, default=str) for r in caplog.records)
    for secret in (INVESTIGATOR_CODE, "guess-guess-guess", headers["Authorization"].split()[1]):
        assert secret not in text
