import itertools
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta

import pytest

from trustbank.domain import ConnectionKind, Dataset, Transaction
from trustbank.fixtures import account_id, build_dataset

NOW = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
FORBIDDEN_WORDS = (
    "mule", "fraud", "scam", "victim", "suspicious", "genuine", "shopkeeper", "complaint",
    "verdict", "flag", "risk", "score", "laundering", "layering",
)  # fmt: skip


def txns_by_id(data: Dataset) -> dict[str, Transaction]:
    return {t.id: t for t in data.transactions}


def test_deterministic_for_same_clock() -> None:
    assert build_dataset(NOW) == build_dataset(NOW)


def test_shifting_the_clock_shifts_every_timestamp_equally() -> None:
    a, b = build_dataset(NOW), build_dataset(NOW + timedelta(days=5))
    shifted = [
        t.timestamp - u.timestamp for t, u in zip(a.transactions, b.transactions, strict=True)
    ]
    assert all(s == timedelta(days=-5) for s in shifted)


def test_requires_timezone_aware_clock() -> None:
    with pytest.raises(ValueError):
        build_dataset(datetime(2026, 10, 14, 12, 0))


def test_counts_match_design() -> None:
    d = build_dataset(NOW)
    assert len(d.customers) == 22
    assert len(d.beneficiaries) == 15
    assert len(d.accounts) == 37
    assert len(d.transactions) == 279
    assert len(d.connections) == 2


def test_ids_unique() -> None:
    d = build_dataset(NOW)
    for items in (d.customers, d.beneficiaries, d.accounts, d.transactions, d.connections):
        ids = [i.id for i in items]
        assert len(ids) == len(set(ids))


def test_referential_integrity() -> None:
    d = build_dataset(NOW)
    accounts = {a.id for a in d.accounts}
    owners = {c.id for c in d.customers} | {b.id for b in d.beneficiaries}
    beneficiaries = {b.id for b in d.beneficiaries}
    assert all(a.owner_id in owners for a in d.accounts)
    assert all(account_id(o) in accounts for o in owners)
    assert all(t.source_account_id in accounts for t in d.transactions)
    assert all(t.beneficiary_id in beneficiaries for t in d.transactions)
    assert all(c.account_a_id in accounts and c.account_b_id in accounts for c in d.connections)


def test_no_future_timestamps_and_no_self_payments() -> None:
    d = build_dataset(NOW)
    assert all(t.timestamp <= NOW for t in d.transactions)
    assert all(t.source_account_id != account_id(t.beneficiary_id) for t in d.transactions)


def test_no_verdicts_labels_or_scenario_identity_in_data() -> None:
    d = build_dataset(NOW)
    text = json.dumps(d.model_dump(mode="json")).lower()
    for word in FORBIDDEN_WORDS:
        assert word not in text, word
    fields = {key for item in d.model_dump(mode="json").values() for row in item for key in row}
    assert not {"complaint_count", "risk", "score", "label", "verdict", "flagged"} & fields


def test_asha_baseline() -> None:
    d = build_dataset(NOW)
    mine = [t for t in d.transactions if t.source_account_id == "acct_asha"]
    assert len(mine) == 9
    assert max(t.amount for t in mine) == 2_500
    assert round(sum(t.amount for t in mine) / 9) == 1_721
    assert len({t.beneficiary_id for t in mine}) == 4


def test_priya_has_two_transactions_and_no_connections() -> None:
    d = build_dataset(NOW)
    mine = [t for t in d.transactions if t.source_account_id == "acct_priya"]
    assert [t.amount for t in mine] == [1_200, 300]
    assert all("priya" not in (c.account_a_id + c.account_b_id) for c in d.connections)


def test_shopkeeper_volume_senders_and_supplier_payments() -> None:
    d = build_dataset(NOW)
    inbound = [t for t in d.transactions if t.beneficiary_id == "ben_sharma_store"]
    assert len(inbound) == 120
    assert len({t.source_account_id for t in inbound}) == 12
    assert all(80 <= t.amount <= 1_800 for t in inbound)
    assert all(10 <= t.timestamp.hour < 20 for t in inbound)
    assert all(NOW - timedelta(days=60) <= t.timestamp < NOW for t in inbound)
    out = [t for t in d.transactions if t.source_account_id == "acct_sharma_store"]
    assert len(out) == 8 and {t.amount for t in out} == {6_000}
    retained = 1 - sum(t.amount for t in out) / sum(t.amount for t in inbound)
    assert 0.5 < retained < 0.65


def test_restaurant_sweeps_most_of_each_day_at_a_fixed_time() -> None:
    d = build_dataset(NOW)
    inbound = [t for t in d.transactions if t.beneficiary_id == "ben_spice_garden"]
    sweeps = [t for t in d.transactions if t.source_account_id == "acct_spice_garden"]
    assert len(inbound) == 60 and len(sweeps) == 20
    assert {(s.timestamp.hour, s.timestamp.minute) for s in sweeps} == {(23, 0)}
    by_day: dict[object, int] = defaultdict(int)
    for t in inbound:
        by_day[t.timestamp.date()] += t.amount
    for s in sweeps:
        day_total = by_day[s.timestamp.date()]
        assert abs(s.amount - 0.95 * day_total) <= 1
        assert all(
            i.timestamp < s.timestamp for i in inbound if i.timestamp.date() == s.timestamp.date()
        )


def test_forwarding_chain_timing_and_retention() -> None:
    d = build_dataset(NOW)
    t = txns_by_id(d)
    for k in range(1, 9):
        chain = [t[f"net_in_{k}"], t[f"net_h1_{k}"], t[f"net_h2_{k}"], t[f"net_h3_{k}"]]
        gaps = [later.timestamp - earlier.timestamp for earlier, later in itertools.pairwise(chain)]
        assert gaps == [timedelta(minutes=m) for m in (6, 4, 5)]
        inbound = chain[0].amount
        assert chain[1].amount >= 0.97 * inbound
        assert chain[3].amount >= 0.95 * inbound


def test_chain_shape_fan_in_and_offramp() -> None:
    d = build_dataset(NOW)
    entry = [t for t in d.transactions if t.beneficiary_id == "ben_novatrade"]
    assert len({t.source_account_id for t in entry}) == 8
    assert not [t for t in d.transactions if t.source_account_id == "acct_swiftassist"]
    assert len([t for t in d.transactions if t.id.startswith("net_")]) == 32
    counts = Counter(c.kind for c in d.connections)
    assert counts == {ConnectionKind.BUSINESS_SUPPLIER: 1, ConnectionKind.SAME_OWNER: 1}


def test_account_ages() -> None:
    d = build_dataset(NOW)
    ben = {b.id: b for b in d.beneficiaries}
    ages = {i: (NOW - b.first_seen_at).days for i, b in ben.items()}
    assert ages["ben_novatrade"] == 3
    assert ages["ben_sharma_store"] == 700
    assert ages["ben_greenleaf"] == 25
    assert all(a.opened_at <= NOW for a in d.accounts)
