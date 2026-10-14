# Capability: Knowledge graph and synthetic scenario data

Shared evidence source for the agents and the investigation console. Concrete fixture values are in `knowledge-graph-data.md`.

**Storage split.** Firestore is the system of record for synthetic application data. Neo4j holds the knowledge graph, a projection of that data built by an ingestion job, and answers graph queries (Cypher). Only the backend accesses either store.

**Principle.** Data only; risk is always computed. Stored data contains facts (who paid whom, how much, when, declared relationships). It never contains complaints, flags, scores, verdicts, or scenario identity. A mule is recognised by how money moves through an account, not by reports against it.

## Requirements

### Requirement: Typed graph schema
The graph SHALL contain exactly these node labels and relationship types.

Node labels: `Customer`, `Account`, `Transaction`, `Beneficiary`, `RiskSignal`.

| Relationship | From → To | Meaning |
|---|---|---|
| `OWNS` | Customer or Beneficiary → Account | Ownership of an account |
| `SENT` | Account → Transaction | Source account of a transaction |
| `PAID` | Transaction → Beneficiary | Recipient of a transaction |
| `CONNECTED_TO` | Account ↔ Account | Declared relationship (`kind`: `SHARED_DEVICE`, `BUSINESS_SUPPLIER`, `SAME_OWNER`) |
| `FLAGGED_FOR` | Transaction → RiskSignal | Signal derived by an agent at assessment time, supported by this transaction |

#### Scenario: Stable identifiers
- GIVEN the graph is ingested from the synthetic data
- THEN every node SHALL have a unique deterministic `id`
- AND ids SHALL be identical between Firestore documents and Neo4j nodes (for example `ben_novatrade`, `txn_hist_1`)
- AND Neo4j uniqueness constraints on `id` SHALL exist for every label
- AND every `CONNECTED_TO` and `FLAGGED_FOR` relationship SHALL have a `provenance`

#### Scenario: Referential integrity
- WHEN ingestion completes
- THEN every relationship endpoint SHALL exist
- AND every Transaction SHALL have exactly one `SENT` and exactly one `PAID` relationship

### Requirement: Evidence provenance
Every relationship, every `RiskSignal`, and every evidence item returned by a query SHALL carry a provenance.

- `VERIFIED_SYNTHETIC`: declared in the fixtures as a fact about a relationship (shared device, supplier link, same owner).
- `INFERRED`: computed from transaction behavior at assessment time (rapid pass-through, low retention, fan-in burst, multi-hop layering, velocity).
- `USER_PROVIDED`: from the customer's questionnaire answers.

#### Scenario: No pre-assigned verdicts or complaints
- THEN seeded graph and Firestore data SHALL NOT contain a fraud label, score, verdict, complaint count, "reported" flag, scenario identity (shopkeeper, mule, low-activity, general), or any seeded `RiskSignal`
- AND behavior-based findings SHALL be computed by queries at assessment time and not stored in advance

#### Scenario: RiskSignals are outputs, not inputs
- WHEN the fraud network agent derives a signal (for example `RAPID_PASS_THROUGH`, `MULTI_HOP_LAYERING`, `FAN_IN_BURST`, `HIGH_VELOCITY`)
- THEN the backend MAY persist it as a `RiskSignal` with `INFERRED` provenance and `FLAGGED_FOR` links to the supporting transactions, for the investigation console
- AND no detection query SHALL read `RiskSignal` nodes as evidence, so earlier assessments cannot influence later ones

#### Scenario: Association is not proof
- THEN every connection and signal SHALL be presented as evidence to investigate
- AND no graph query SHALL return a "guilty" or "fraudulent" verdict

### Requirement: Mule behavior is derived from raw transactions
Fixtures SHALL contain raw transactions with minute-precision timestamps, sufficient for queries to compute:

- **Dwell time:** time between funds arriving in an account and leaving it, matched first-in-first-out.
- **Retention:** share of inflow still in the account at the end of a window.
- **Velocity:** transaction count in a window.
- **Fan-in / fan-out:** distinct senders and distinct destinations in a window.
- **Layering:** forwarding chains across accounts where each hop follows the previous within a short gap, ending at an account with no onward transfers.
- **Account age:** a supporting factor only.

### Requirement: Synthetic scenarios and data
Fixtures SHALL be deterministic (no randomness; timestamps relative to an injectable clock). Outcomes SHALL emerge from running the real queries and agents. The full table (ids, amounts, timing, generator rules) is in `knowledge-graph-data.md`. Ten payment scenarios are covered:

| # | Payment | Purpose |
|---|---|---|
| S1 | Asha → Rahul, ₹2,500 | Routine payment |
| S2 | Asha → Sharma General Store, ₹1,200 | Genuine shopkeeper |
| S3 | Priya → Sharma General Store, ₹400 | Low-activity payer to a shopkeeper |
| S4 | Priya → Ananya, ₹600 | Low-activity, known recipient |
| S5 | Asha → Green Leaf Bakery, ₹450 | Genuine new business |
| S6 | Asha → Heritage Jewellers, ₹40,000 | Anomaly only, clean recipient |
| S7 | Asha → Spice Garden Restaurant, ₹1,800 | High pass-through that is not a mule |
| S8 | Asha → Nova Trade Desk, ₹25,000 | Mule network entry account |
| S9 | Priya → Nova Trade Desk, ₹8,000 | Thin-history payer, same network |
| S10 | Asha → Quick Returns Hub, ₹5,000 | Mule network, mid-chain account |

#### Scenario: Genuine shopkeeper (`ben_sharma_store`)
- GIVEN a beneficiary first seen about 700 days ago
- THEN the data SHALL contain about 120 completed inbound payments over 60 days from 12 distinct customers, amounts ₹80–₹1,800, during business hours
- AND 8 weekly outbound payments of ₹6,000 to `ben_wholesale_hub` (about 900 days old), unrelated in timing to individual inbound payments
- AND a `VERIFIED_SYNTHETIC` `CONNECTED_TO` of kind `BUSINESS_SUPPLIER` between the two accounts
- AND queries SHALL show long dwell (days) and about 57% retention, so nothing is flagged because of behavior, not because of a label

#### Scenario: Mule network (`ben_novatrade`, `ben_quickreturns`, `ben_taskrewards`, `ben_swiftassist`)
- THEN `ben_novatrade` SHALL be about 3 days old and have no stored signal, flag, or complaint
- AND 8 victim customers SHALL each pay `ben_novatrade`, and each amount SHALL be forwarded `ben_novatrade` → `ben_quickreturns` → `ben_taskrewards` → `ben_swiftassist` with gaps of about 6, 4 and 5 minutes, keeping 1–2% at each hop
- AND `ben_swiftassist` SHALL have no onward transfers
- AND no `CONNECTED_TO` relationship SHALL exist between mule accounts
- AND at least two independent behaviors (low dwell, low retention, fan-in, layering, velocity) SHALL be detectable

#### Scenario: High pass-through that is not a mule (`ben_spice_garden`)
- THEN the account SHALL be about 500 days old with about 3 inbound payments per day for 20 days
- AND a daily sweep at 23:00 of about 95% of that day's inbound to `ben_spice_owner`, joined by a `VERIFIED_SYNTHETIC` `SAME_OWNER` connection
- AND dwell SHALL be hours, there SHALL be one hop only, and the schedule SHALL be regular

#### Scenario: Genuine new business (`ben_greenleaf`)
- THEN the account SHALL be about 25 days old with 8 small inbound payments, no outflow, and nothing else unusual

#### Scenario: Established high-ticket merchant (`ben_heritage`)
- THEN the account SHALL be about 600 days old with about 20 inbound payments of ₹5,000–₹60,000 and no outflow

#### Scenario: Low-activity customer (`cust_priya`, "Priya Nair")
- THEN exactly 2 completed transactions: ₹1,200 to `ben_ananya` about 20 days ago; ₹300 to `ben_metrocafe` about 8 days ago
- AND no `CONNECTED_TO` relationships
- AND limited history SHALL NOT be represented as a risk signal

#### Scenario: General customer (`cust_asha`, "Asha Menon")
- THEN 9 completed transactions to 4 beneficiaries (rent ₹2,500 monthly, groceries, electricity, cafe) providing the baseline (average, maximum, count, usual recipients)

#### Scenario: Demo personas
- THEN fixtures SHALL include demo personas (`cust_asha`, `cust_priya`) selectable at dummy entry; no passwords or credentials exist in the data

### Requirement: Scenario registry (tests only)
A fixtures-level registry SHALL list scenarios and primary entity ids for tests and demos. It SHALL NOT be accessible to agents, tools, or API responses, and SHALL NOT contain verdicts used at runtime.

### Requirement: Graph queries (Cypher)
`GraphService` SHALL provide read-only parameterized queries returning evidence with provenance:

- `get_node(id)`, `neighbors(id, rel_types?)`
- `transaction_neighborhood(txn_id)`: transaction, sender account and owner, beneficiary and account, declared `CONNECTED_TO` accounts, and accounts reached by forwarding chains within 3 hops of the beneficiary account, with owners. It SHALL NOT return the whole graph.
- `account_age_days(account_id, as_of)`
- `recent_senders(account_id, window_hours, as_of)`: distinct senders, count, total
- `flow_profile(account_id, window_hours, as_of)`: inbound count and total, outbound count and total, distinct destinations, retention ratio, median and maximum dwell (FIFO), velocity
- `forwarding_chain(account_id, window_hours, as_of, max_hops ≤ 4, max_gap_minutes)`: onward chains where each hop follows the previous within the gap, with per-hop amount, dwell, and whether the final account has no onward transfers

#### Scenario: Bounded neighborhood
- WHEN `transaction_neighborhood` is called with a transaction id
- THEN the result SHALL contain only entities reachable by the stated rules and identify which ids are highlighted evidence

#### Scenario: Unknown id
- THEN queries SHALL return an explicit not-found result

#### Scenario: Injection safety
- THEN all values SHALL be Cypher parameters, never concatenated

### Requirement: Persistence, seeding, and ingestion
- Customers, accounts, beneficiaries, and transactions SHALL be stored in Firestore (Native mode). The browser SHALL NOT access Firestore or Neo4j; `firestore.rules` SHALL deny all client access.
- The seed command SHALL write fixtures to Firestore with deterministic ids, then run ingestion into Neo4j (constraints, then `MERGE` nodes and relationships). Running it twice SHALL give identical data. A reset option SHALL clear only seeded data.
- When a payment completes, the backend SHALL write the transaction to Firestore and project it into Neo4j.
- Local development and tests SHALL use the Firestore emulator and a Neo4j container. Deployed runs SHALL use Application Default Credentials for Firestore and Neo4j credentials from configuration or Secret Manager.

#### Scenario: Reproducible
- GIVEN the same fixtures and clock
- WHEN the seed runs twice
- THEN node ids, relationship ids, and documents SHALL be identical

### Requirement: Synthetic-only
All entities, amounts, and relationships SHALL be fictional and identified as simulated.
