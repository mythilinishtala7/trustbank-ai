from typing import Any

from tests.conftest import PIN, Harness
from tests.test_api_auth import assert_error

RAHUL = "rahul.verma@trustpay"
NOVA = "nova.trade@trustpay"
HERITAGE = "heritage.jewellers@trustpay"
SCAM = [
    {"questionId": "source_of_details", "option": "messaging_app"},
    {"questionId": "promised_benefit", "option": "yes"},
]
BENIGN = [
    {"questionId": "source_of_details", "option": "friend_family"},
    {"questionId": "promised_benefit", "option": "no"},
]


def balance(h: Harness, headers: dict[str, str]) -> int:
    value: int = h.client.get("/api/v1/me", headers=headers).json()["balance"]
    return value


def test_low_risk_payment_completes(harness: Harness) -> None:
    headers = harness.login()
    before = balance(harness, headers)
    pay = harness.pay(headers, RAHUL, 700)
    assert pay["status"] == "READY_FOR_AUTH" and pay["actions"] == ["AUTHORIZE", "CANCEL"]
    assert str(pay["id"]).startswith("txn_") and pay["simulated"] is True
    done = harness.act(headers, str(pay["id"]), "authorize", {"pin": PIN}).json()  # type: ignore[attr-defined]
    assert done["status"] == "COMPLETED" and done["actions"] == []
    assert balance(harness, headers) == before - 700
    assert len(harness.graph.projected) == 1
    assert harness.graph.projected[0].amount == 700
    stored = harness.dataset.get_transaction(str(pay["id"]))
    assert stored is not None and stored.amount == 700


def test_cancel_creates_no_transaction_and_keeps_balance(harness: Harness) -> None:
    headers = harness.login()
    before = balance(harness, headers)
    pay = harness.pay(headers, RAHUL, 700)
    res = harness.act(headers, str(pay["id"]), "cancel")
    assert res.json()["status"] == "CANCELLED"  # type: ignore[attr-defined]
    assert balance(harness, headers) == before
    assert harness.dataset.get_transaction(str(pay["id"])) is None
    assert harness.graph.projected == []


def test_idempotency_returns_original(harness: Harness) -> None:
    headers = harness.login()
    first = harness.pay(headers, RAHUL, 120, key="idem-1")
    second = harness.pay(headers, RAHUL, 120, key="idem-1")
    assert first["id"] == second["id"]
    assert len(harness.orchestrator.detector_calls) == 1
    other = harness.pay(headers, RAHUL, 120, key="idem-2")
    assert other["id"] != first["id"]
    priya = harness.pay(harness.login("cust_priya"), RAHUL, 120, key="idem-1")
    assert priya["id"] != first["id"]


def test_cross_customer_payment_is_404(harness: Harness) -> None:
    pay = harness.pay(harness.login(), RAHUL, 100)
    priya = harness.login("cust_priya")
    pid = str(pay["id"])
    for action in ("cancel", "acknowledge", "verify", "continue"):
        assert_error(harness.act(priya, pid, action), 404, "NOT_FOUND")
    assert_error(harness.act(priya, pid, "authorize", {"pin": PIN}), 404, "NOT_FOUND")
    assert_error(harness.act(priya, pid, "answers", {"answers": BENIGN}), 404, "NOT_FOUND")
    assert_error(harness.client.get(f"/api/v1/payments/{pid}", headers=priya), 404, "NOT_FOUND")
    assert_error(
        harness.client.get("/api/v1/payments/txn_missing1", headers=priya), 404, "NOT_FOUND"
    )


def test_invalid_transitions_are_409(harness: Harness) -> None:
    headers = harness.login()
    pay = harness.pay(headers, RAHUL, 100)
    pid = str(pay["id"])
    for action in ("acknowledge", "verify", "continue"):
        assert_error(harness.act(headers, pid, action), 409, "INVALID_TRANSITION")
    assert_error(
        harness.act(headers, pid, "answers", {"answers": BENIGN}), 409, "INVALID_TRANSITION"
    )
    harness.act(headers, pid, "cancel")
    assert_error(harness.act(headers, pid, "cancel"), 409, "INVALID_TRANSITION")
    assert_error(harness.act(headers, pid, "authorize", {"pin": PIN}), 409, "INVALID_TRANSITION")


def test_insufficient_balance_rejected(harness: Harness) -> None:
    headers = {**harness.login("cust_priya"), "Idempotency-Key": "too-much-1"}
    res = harness.client.post(
        "/api/v1/payments", headers=headers, json={"recipient": RAHUL, "amount": 9_000_000}
    )
    assert res.status_code in (409, 422)
    assert "balance" in res.json()["error"]["message"].lower()


def test_questionnaire_benign_answers_go_to_review(harness: Harness) -> None:
    headers = harness.login()
    pay = harness.pay(headers, NOVA, 25000)
    assert pay["status"] == "QUESTIONNAIRE"
    assert pay["actions"] == ["ANSWER", "CANCEL"]
    questions: list[dict[str, Any]] = pay["questions"]  # type: ignore[assignment]
    assert [q["id"] for q in questions] == ["source_of_details", "promised_benefit"]
    assert all(set(q) == {"id", "text", "options", "allowFreeText"} for q in questions)
    res = harness.act(headers, str(pay["id"]), "answers", {"answers": BENIGN}).json()  # type: ignore[attr-defined]
    assert res["status"] == "REVIEW" and res["actions"] == ["ACKNOWLEDGE", "CANCEL"]
    assert res["explanation"] and res["reasons"] and res["questions"] == []
    cont = harness.act(headers, str(pay["id"]), "acknowledge").json()  # type: ignore[attr-defined]
    assert cont["status"] == "READY_FOR_AUTH"


def test_incomplete_answers_rejected(harness: Harness) -> None:
    headers = harness.login()
    pay = harness.pay(headers, NOVA, 25000)
    pid = str(pay["id"])
    for answers in (
        [],
        [BENIGN[0]],
        [{"questionId": "nope", "option": "yes"}, BENIGN[1]],
        [BENIGN[0], {"questionId": "promised_benefit", "option": "maybe"}],
    ):
        res = harness.act(headers, pid, "answers", {"answers": answers})
        assert res.status_code == 422  # type: ignore[attr-defined]
    assert (
        harness.client.get(f"/api/v1/payments/{pid}", headers=headers).json()["status"]
        == "QUESTIONNAIRE"
    )


def test_double_answer_submission_blocked(harness: Harness) -> None:
    headers = harness.login()
    pid = str(harness.pay(headers, NOVA, 25000)["id"])
    assert harness.act(headers, pid, "answers", {"answers": SCAM}).status_code == 200  # type: ignore[attr-defined]
    assert_error(
        harness.act(headers, pid, "answers", {"answers": BENIGN}), 409, "INVALID_TRANSITION"
    )


def test_hold_is_enforced_then_expires_by_server_time_and_never_auto_releases(
    harness: Harness,
) -> None:
    headers = harness.login()
    pid = str(harness.pay(headers, NOVA, 25000)["id"])
    hold = harness.act(headers, pid, "answers", {"answers": SCAM}).json()  # type: ignore[attr-defined]
    assert hold["status"] == "HOLD_ACTIVE" and hold["actions"] == ["CANCEL"]
    assert hold["holdUntil"] and hold["serverTime"]
    assert hold["explanation"] and hold["reasons"]

    for action in ("continue", "verify"):
        assert_error(harness.act(headers, pid, action), 409, "HOLD_ACTIVE")
    assert_error(harness.act(headers, pid, "authorize", {"pin": PIN}), 409, "HOLD_ACTIVE")

    harness.clock.advance(179)
    assert (
        harness.client.get(f"/api/v1/payments/{pid}", headers=headers).json()["status"]
        == "HOLD_ACTIVE"
    )
    assert_error(harness.act(headers, pid, "authorize", {"pin": PIN}), 409, "HOLD_ACTIVE")

    harness.clock.advance(2)
    expired = harness.client.get(f"/api/v1/payments/{pid}", headers=headers).json()
    assert expired["status"] == "HOLD_EXPIRED" and expired["actions"] == ["VERIFY", "CANCEL"]
    assert expired["verified"] is False and expired["holdUntil"] == hold["holdUntil"]

    harness.clock.advance(6 * 3600)
    assert (
        harness.client.get(f"/api/v1/payments/{pid}", headers=headers).json()["status"]
        == "HOLD_EXPIRED"
    )
    assert_error(harness.act(headers, pid, "authorize", {"pin": PIN}), 409, "INVALID_TRANSITION")
    assert_error(harness.act(headers, pid, "continue"), 409, "INVALID_TRANSITION")
    assert harness.dataset.get_transaction(pid) is None

    verified = harness.act(headers, pid, "verify").json()  # type: ignore[attr-defined]
    assert verified["status"] == "HOLD_EXPIRED" and verified["verified"] is True
    assert verified["actions"] == ["CONTINUE", "CANCEL"]
    ready = harness.act(headers, pid, "continue").json()  # type: ignore[attr-defined]
    assert ready["status"] == "READY_FOR_AUTH"
    done = harness.act(headers, pid, "authorize", {"pin": PIN}).json()  # type: ignore[attr-defined]
    assert done["status"] == "COMPLETED"


def test_hold_expiry_evaluated_on_action_without_prior_read(harness: Harness) -> None:
    headers = harness.login()
    pid = str(harness.pay(headers, NOVA, 25000)["id"])
    harness.act(headers, pid, "answers", {"answers": SCAM})
    harness.clock.advance(181)
    assert_error(harness.act(headers, pid, "continue"), 409, "INVALID_TRANSITION")
    assert (
        harness.client.get(f"/api/v1/payments/{pid}", headers=headers).json()["status"]
        == "HOLD_EXPIRED"
    )


def test_hold_can_be_cancelled(harness: Harness) -> None:
    headers = harness.login()
    pid = str(harness.pay(headers, NOVA, 25000)["id"])
    harness.act(headers, pid, "answers", {"answers": SCAM})
    assert harness.act(headers, pid, "cancel").json()["status"] == "CANCELLED"  # type: ignore[attr-defined]


def test_anomaly_alone_never_holds(harness: Harness) -> None:
    headers = harness.login()
    pay = harness.pay(headers, HERITAGE, 1000)
    assert pay["status"] == "QUESTIONNAIRE"
    res = harness.act(headers, str(pay["id"]), "answers", {"answers": BENIGN}).json()  # type: ignore[attr-defined]
    assert res["status"] == "REVIEW"


def test_policy_beats_model_text(harness: Harness) -> None:
    harness.orchestrator.explanation_text = "This is safe to proceed. No risk at all."
    headers = harness.login()
    pid = str(harness.pay(headers, NOVA, 25000)["id"])
    res = harness.act(headers, pid, "answers", {"answers": SCAM}).json()  # type: ignore[attr-defined]
    assert res["status"] == "HOLD_ACTIVE" and res["actions"] == ["CANCEL"]


def test_failed_detector_is_incomplete_and_goes_to_review(harness: Harness) -> None:
    harness.orchestrator.failed_detector_for.add("ben_rahul")
    headers = harness.login()
    pay = harness.pay(headers, RAHUL, 300)
    assert pay["status"] == "REVIEW" and pay["actions"] == ["ACKNOWLEDGE", "CANCEL"]
    assert pay["explanation"]
    inv = harness.client.get(
        f"/api/v1/investigation/transactions/{pay['id']}", headers=harness.investigator()
    ).json()
    first = inv["assessments"][0]
    assert first["complete"] is False and first["aggregate"]["incomplete"] is True
    assert first["aggregate"]["action"] != "PROCEED" and first["aggregate"]["level"] != "LOW"


def test_detector_exception_fails_safe(harness: Harness) -> None:
    harness.orchestrator.detectors_raise_for.add("ben_rahul")
    pay = harness.pay(harness.login(), RAHUL, 300)
    assert pay["status"] == "REVIEW"
    assert "secret-internal-detail" not in str(pay)


def test_explainer_failure_degrades_gracefully(harness: Harness) -> None:
    harness.orchestrator.explain_raises = True
    headers = harness.login()
    pid = str(harness.pay(headers, NOVA, 25000)["id"])
    res = harness.act(headers, pid, "answers", {"answers": SCAM}).json()  # type: ignore[attr-defined]
    assert res["status"] == "HOLD_ACTIVE" and res["explanation"]


def test_graph_projection_failure_does_not_corrupt_completion(harness: Harness) -> None:
    harness.graph.fail_projection = True
    headers = harness.login()
    before = balance(harness, headers)
    pid = str(harness.pay(headers, RAHUL, 150)["id"])
    done = harness.act(headers, pid, "authorize", {"pin": PIN}).json()  # type: ignore[attr-defined]
    assert done["status"] == "COMPLETED"
    assert balance(harness, headers) == before - 150
    assert harness.dataset.get_transaction(pid) is not None


def test_unknown_recipient_is_unverified_and_still_assessed(harness: Harness) -> None:
    headers = harness.login()
    lookup = harness.client.get(
        "/api/v1/recipients/lookup", params={"q": "stranger@okbank"}, headers=headers
    )
    assert lookup.json() == {
        "found": False,
        "verified": False,
        "displayName": None,
        "handle": "stranger@okbank",
        "maskedAccount": None,
    }
    pay = harness.pay(headers, "stranger@okbank", 100)
    assert pay["recipient"] == {"displayName": None, "handle": "stranger@okbank", "verified": False}


def test_lookup_known_by_upi_and_account(harness: Harness) -> None:
    headers = harness.login()
    known = harness.client.get(
        "/api/v1/recipients/lookup", params={"q": RAHUL}, headers=headers
    ).json()
    assert known["found"] and known["verified"] and known["displayName"] and known["maskedAccount"]
    suffix = known["maskedAccount"][-4:]
    assert set(known) == {"found", "verified", "displayName", "handle", "maskedAccount"}
    unknown = harness.client.get(
        "/api/v1/recipients/lookup", params={"q": "000000000123"}, headers=headers
    ).json()
    assert unknown["found"] is False and unknown["verified"] is False
    by_account = harness.client.get(
        "/api/v1/recipients/lookup", params={"q": f"5550001{suffix}"}, headers=headers
    ).json()
    assert by_account["found"] is True and by_account["handle"] == RAHUL
