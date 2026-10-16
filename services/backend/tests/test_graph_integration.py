"""Knowledge graph integration tests against the running Neo4j (raw facts, bounds, writes)."""

from datetime import timedelta

from tests import support_graph
from tests.support_graph import NOW, GraphEnv
from trustbank.contracts import Evidence
from trustbank.domain import Provenance, Transaction
from trustbank.graph.ingest import check_integrity, ingest_dataset
from trustbank.graph.schema import NODE_LABELS, REL_TYPES

graph_env = support_graph.graph_env


def test_integrity_and_idempotent_ingest(graph_env: GraphEnv) -> None:
    driver = graph_env.graph._driver
    assert check_integrity(driver, graph_env.dataset) == []
    before = _counts(graph_env)
    ingest_dataset(driver, graph_env.dataset)
    assert _counts(graph_env) == before
    d = graph_env.dataset
    assert before["nodes"] == (
        len(d.customers) + len(d.beneficiaries) + len(d.accounts) + len(d.transactions)
    )


def _counts(env: GraphEnv) -> dict[str, int]:
    rows, _, _ = env.graph._driver.execute_query(
        "MATCH (n) WITH count(n) AS nodes MATCH ()-[r]->() RETURN nodes, count(r) AS rels"
    )
    return {"nodes": rows[0]["nodes"], "rels": rows[0]["rels"]}


def test_schema_has_only_spec_labels_and_no_verdicts(graph_env: GraphEnv) -> None:
    driver = graph_env.graph._driver
    labels = {r[0] for r in driver.execute_query("CALL db.labels()")[0]}
    types = {r[0] for r in driver.execute_query("CALL db.relationshipTypes()")[0]}
    keys = {r[0] for r in driver.execute_query("CALL db.propertyKeys()")[0]}
    assert labels <= set(NODE_LABELS)
    assert types <= set(REL_TYPES)
    assert not {
        k for k in keys if any(w in k.lower() for w in ("fraud", "mule", "verdict", "scenario"))
    }
    rows, _, _ = driver.execute_query(
        "MATCH (n) UNWIND [k IN keys(n) | toString(n[k])] AS v "
        "WITH v WHERE toLower(v) CONTAINS 'mule' OR toLower(v) CONTAINS 'fraud' "
        "OR toLower(v) CONTAINS 'scenario' RETURN count(v) AS bad"
    )
    assert rows[0]["bad"] == 0


def test_every_relationship_carries_provenance(graph_env: GraphEnv) -> None:
    rows, _, _ = graph_env.graph._driver.execute_query(
        "MATCH ()-[r]->() WHERE r.provenance IS NULL OR r.id IS NULL RETURN count(r) AS bad"
    )
    assert rows[0]["bad"] == 0


def test_raw_facts_for_forwarding_chain_entry(graph_env: GraphEnv) -> None:
    g = graph_env.graph
    account = g.account_for_owner("ben_novatrade")
    assert account == "acct_novatrade"
    assert g.account_age_days(account, NOW) == 3
    senders = g.recent_senders(account, 72, NOW)
    assert senders.distinct_senders == 8 and senders.transaction_count == 8
    flow = g.flow_profile(account, 168, NOW)
    assert flow.inbound_count == 8 and flow.outbound_count == 8
    assert flow.median_dwell_minutes is not None and flow.median_dwell_minutes <= 10
    assert flow.retention_ratio is not None and flow.retention_ratio < 0.05
    assert flow.distinct_destinations == 1
    chains = g.forwarding_chain(account, 168, NOW)
    deepest = max(chains.chains, key=lambda c: len(c.hops))
    assert [round(h.gap_minutes or 0) for h in deepest.hops] == [6, 4, 5]
    assert deepest.terminal_account_id == "acct_swiftassist"
    assert not deepest.terminal_has_onward


def test_account_ages(graph_env: GraphEnv) -> None:
    g = graph_env.graph
    ages = {
        owner: g.account_age_days(g.account_for_owner(owner) or "", NOW)
        for owner in ("ben_novatrade", "ben_quickreturns", "ben_taskrewards", "ben_swiftassist")
    }
    assert ages == {
        "ben_novatrade": 3,
        "ben_quickreturns": 6,
        "ben_taskrewards": 11,
        "ben_swiftassist": 9,
    }


def test_shop_holds_money_for_days_and_retains_it(graph_env: GraphEnv) -> None:
    g = graph_env.graph
    shop = g.flow_profile("acct_sharma_store", 1464, NOW)
    assert shop.distinct_senders >= 10
    assert shop.median_dwell_minutes is not None and shop.median_dwell_minutes > 24 * 60
    assert shop.retention_ratio is not None and 0.45 <= shop.retention_ratio <= 0.7


def test_restaurant_passes_funds_on_slowly_on_a_schedule(graph_env: GraphEnv) -> None:
    g = graph_env.graph
    flow = g.flow_profile("acct_spice_garden", 168, NOW)
    assert flow.outflow_ratio is not None and flow.outflow_ratio >= 0.8
    assert flow.median_dwell_minutes is not None and 180 <= flow.median_dwell_minutes <= 600
    assert flow.regular_schedule
    assert g.forwarding_chain("acct_spice_garden", 168, NOW).max_depth == 1


def test_unknown_ids_are_not_found(graph_env: GraphEnv) -> None:
    g = graph_env.graph
    assert not g.get_node("nope").found
    assert not g.neighbors("nope").found
    assert g.account_for_owner("ben_missing") is None
    assert g.account_age_days("acct_missing", NOW) is None
    assert not g.flow_profile("acct_missing", 72, NOW).found
    assert not g.transaction_neighborhood("missing").found


def test_declared_connections_are_verified_context(graph_env: GraphEnv) -> None:
    result = graph_env.graph.neighbors("acct_spice_garden", ["CONNECTED_TO"])
    assert [n.kind for n in result.neighbors] == ["SAME_OWNER"]
    assert result.neighbors[0].provenance is Provenance.VERIFIED_SYNTHETIC


def test_transaction_neighborhood_is_bounded(graph_env: GraphEnv) -> None:
    hood = graph_env.graph.transaction_neighborhood("net_in_8", hops=3)
    assert hood.found
    assert len(hood.entities) < 60
    assert "net_in_8" in hood.highlighted_ids or any(e.id == "net_in_8" for e in hood.entities)


def test_investigation_graph_is_bounded_and_highlights(graph_env: GraphEnv) -> None:
    g = graph_env.graph
    view = g.investigation_graph(
        customer_id="cust_asha",
        beneficiary_id="ben_novatrade",
        transaction_id=None,
        highlight_ids=["ben_novatrade", "acct_novatrade"],
    )
    ids = {n.id for n in view.nodes}
    assert {"cust_asha", "ben_novatrade", "acct_novatrade", "acct_quickreturns"} <= ids
    assert all(e.source in ids and e.target in ids for e in view.edges)
    assert len(view.nodes) <= 80
    total = _counts(graph_env)["nodes"]
    assert len(view.nodes) < total / 3
    assert {n.id for n in view.nodes if n.highlighted} >= {"ben_novatrade", "acct_novatrade"}
    assert any(e.highlighted and e.type == "OWNS" for e in view.edges)

    small = g.investigation_graph(
        customer_id="cust_asha",
        beneficiary_id="ben_novatrade",
        transaction_id=None,
        highlight_ids=[],
        max_nodes=10,
    )
    assert len(small.nodes) <= 10 and small.truncated
    assert all(e.source in {n.id for n in small.nodes} for e in small.edges)


def test_project_transaction_is_idempotent(graph_env: GraphEnv) -> None:
    g = graph_env.graph
    txn = Transaction(
        id="live_txn_1",
        source_account_id="acct_asha",
        beneficiary_id="ben_rahul",
        amount=2500,
        note="Rent",
        timestamp=NOW,
    )
    try:
        before = _counts(graph_env)
        assert g.project_transaction(txn)
        assert g.project_transaction(txn)
        after = _counts(graph_env)
        assert after == {"nodes": before["nodes"] + 1, "rels": before["rels"] + 2}
        missing = txn.model_copy(update={"id": "live_txn_2", "beneficiary_id": "ben_missing"})
        assert not g.project_transaction(missing)
    finally:
        g._driver.execute_query("MATCH (t:Transaction {id: 'live_txn_1'}) DETACH DELETE t")


def test_signals_are_outputs_and_never_change_detection(graph_env: GraphEnv) -> None:
    g = graph_env.graph
    account = "acct_novatrade"
    before = (
        g.flow_profile(account, 168, NOW),
        g.recent_senders(account, 72, NOW),
        g.forwarding_chain(account, 168, NOW),
    )
    evidence = [
        Evidence(
            id="network.rapid_pass_through",
            summary="forwarded within minutes",
            provenance=Provenance.INFERRED,
            source_entity_ids=["net_in_8", "net_h1_8"],
            points=20,
        ),
        Evidence(
            id="anomaly.amount_deviation",
            summary="not a network signal",
            provenance=Provenance.INFERRED,
            points=50,
        ),
    ]
    try:
        assert g.record_signals("net_in_8", "ben_novatrade", evidence) == 1
        assert g.record_signals("net_in_8", "ben_novatrade", evidence) == 1
        rows, _, _ = g._driver.execute_query(
            "MATCH (t:Transaction)-[f:FLAGGED_FOR]->(r:RiskSignal) "
            "RETURN r.id AS id, f.provenance AS p, collect(t.id) AS txns"
        )
        assert [r["id"] for r in rows] == ["sig_ben_novatrade_rapid_pass_through"]
        assert rows[0]["p"] == "INFERRED" and set(rows[0]["txns"]) == {"net_in_8", "net_h1_8"}
        view = g.investigation_graph(
            customer_id="cust_asha",
            beneficiary_id="ben_novatrade",
            transaction_id=None,
            highlight_ids=[],
        )
        assert any(n.label == "RiskSignal" for n in view.nodes)
        after = (
            g.flow_profile(account, 168, NOW),
            g.recent_senders(account, 72, NOW),
            g.forwarding_chain(account, 168, NOW),
        )
        assert after == before
    finally:
        g._driver.execute_query("MATCH (r:RiskSignal) DETACH DELETE r")


def test_flow_profile_is_window_bounded(graph_env: GraphEnv) -> None:
    g = graph_env.graph
    later = NOW + timedelta(days=30)
    assert g.flow_profile("acct_novatrade", 72, later).inbound_count == 0
