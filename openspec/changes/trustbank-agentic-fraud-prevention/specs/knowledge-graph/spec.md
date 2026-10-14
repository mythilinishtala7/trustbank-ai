# Capability: Knowledge graph and synthetic scenario data

Shared evidence source for the agents and the investigation console.

**Storage split.** Firestore is the system of record for synthetic application data. Neo4j holds the knowledge graph, a projection of that data built by an ingestion job, and answers graph queries (Cypher). Only the backend accesses either store.

## Requirements

### Requirement: Typed graph schema
The graph SHALL contain exactly these node labels and relationship types.

Node labels: `Customer`, `Account`, `Transaction`, `Beneficiary`, `RiskSignal`.

| Relationship | From → To | Meaning |
|---|---|---|
| `OWNS` | Customer or Beneficiary → Account | Ownership of an account |
| `SENT` | Account → Transaction | Source account of a transaction |
| `PAID` | Transaction → Beneficiary | Recipient of a transaction |
| `CONNECTED_TO` | Account ↔ Account | Declared relationship (`kind`: `SHARED_DEVICE`, `BUSINESS_SUPPLIER`) |
| `FLAGGED_FOR` | Transaction → RiskSignal | Stored reported intelligence attached to a transaction |

#### Scenario: Stable identifiers
- GIVEN the graph is ingested from the synthetic data
- THEN every node SHALL have a unique deterministic `id`
- AND ids SHALL be identical between Firestore documents and Neo4j nodes (for example `ben_novatrade`, `txn_hist_1`)
- AND Neo4j uniqueness constraints on `id` SHALL exist for every label
- AND every stored `CONNECTED_TO` and `FLAGGED_FOR` relationship SHALL have a `provenance`

#### Scenario: Referential integrity
- WHEN ingestion completes
- THEN every relationship endpoint SHALL exist
- AND every Transaction SHALL have exactly one `SENT` and exactly one `PAID` relationship

### Requirement: Evidence provenance
Every stored relationship, every `RiskSignal`, and every evidence item returned by a query SHALL carry a provenance.

- `VERIFIED_SYNTHETIC`: declared in the fixtures as reported intelligence (complaint-based flag, shared device, supplier relationship).
- `INFERRED`: computed at query time from transaction behavior (fan-in burst, pass-through, multi-hop link to a reported account).

#### Scenario: No pre-assigned verdicts
- THEN the graph and Firestore documents readable by agents SHALL NOT contain a fraud label, score, verdict, or scenario identity (shopkeeper, fraudulent, low-activity, general)
- AND behavior-based findings SHALL be computed by queries at assessment time and not stored in advance

#### Scenario: Association is not proof
- THEN every connection and signal SHALL be presented as evidence to investigate
- AND no graph query SHALL return a "guilty" or "fraudulent" verdict

### Requirement: Four synthetic scenarios
Fixtures SHALL be deterministic (no randomness; timestamps relative to an injectable clock). Outcomes SHALL emerge from running the real queries and agents.

#### Scenario: Genuine shopkeeper (`ben_sharma_store`, "Sharma General Store")
- GIVEN a beneficiary first seen about 700 days ago with no complaints
- THEN the data SHALL contain about 45 completed inbound payments in the last 60 days from at least 10 distinct customers, amounts ₹80–₹1,800
- AND about 4 weekly outbound payments of ₹25,000 to a supplier (`ben_wholesale_hub`, about 900 days old)
- AND a `VERIFIED_SYNTHETIC` `CONNECTED_TO` of kind `BUSINESS_SUPPLIER` between the two accounts
- AND the fraud queries SHALL find nothing suspicious because the account is established and has no links to reported accounts, not because it is labelled benign

#### Scenario: Fraudulent network (`ben_novatrade`, `ben_mule_a`, `ben_mule_b`, `ben_mule_c`)
- THEN `ben_novatrade` SHALL be about 3 days old, with zero complaints and no stored `RiskSignal`
- AND the three mule beneficiaries SHALL have stored `VERIFIED_SYNTHETIC` `RECIPIENT_REPORTED` signals (with complaint counts) attached via `FLAGGED_FOR` to transactions they received
- AND at least one `VERIFIED_SYNTHETIC` `CONNECTED_TO` of kind `SHARED_DEVICE` SHALL exist between two mule accounts
- AND the raw transfers SHALL exist so queries can detect fan-in (3 or more distinct senders into `ben_novatrade` within 72 hours), pass-through (at least 50% of inflow forwarded onward within 72 hours), and links to reported accounts
- AND at least two independent evidence types SHALL be detectable

#### Scenario: Low-activity customer (`cust_priya`, "Priya Nair")
- THEN exactly 2 completed transactions: ₹1,200 to new beneficiary `ben_ananya` about 20 days ago; ₹300 to `ben_metrocafe` about 8 days ago
- AND no `CONNECTED_TO` or `FLAGGED_FOR` relationships
- AND limited history SHALL NOT be represented as a risk signal

#### Scenario: General customer (`cust_asha`, "Asha Menon")
- THEN 9 completed transactions to 4 beneficiaries (rent ₹2,500 monthly, groceries, electricity, cafe) providing the baseline (average, maximum, count, usual recipients)
- AND no `FLAGGED_FOR` relationships on her history

#### Scenario: Demo personas
- THEN fixtures SHALL include demo personas (`cust_asha`, `cust_priya`) selectable at dummy entry; no passwords or credentials exist in the data

### Requirement: Scenario registry (tests only)
A fixtures-level registry SHALL list scenarios and primary entity ids for tests and demos. It SHALL NOT be accessible to agents, tools, or API responses, and SHALL NOT contain verdicts used at runtime.

### Requirement: Graph queries (Cypher)
`GraphService` SHALL provide read-only parameterized queries returning evidence with provenance:

- `get_node(id)`, `neighbors(id, rel_types?)`
- `transaction_neighborhood(txn_id)`: transaction, sender account and owner, beneficiary and account, stored signals, and `CONNECTED_TO` accounts up to 2 hops from the beneficiary account with owners. It SHALL NOT return the whole graph.
- `recent_senders(account_id, window_hours, as_of)`
- `pass_through(account_id, window_hours, as_of)`: inbound total, outbound total, destinations
- `links_to_flagged(account_id, max_hops ≤ 3)`: paths to accounts with stored reported signals, with provenance per hop
- `account_age_days(account_id, as_of)`

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
