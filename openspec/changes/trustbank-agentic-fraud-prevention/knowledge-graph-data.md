# Knowledge graph data design (for review)

Concrete synthetic data behind `specs/knowledge-graph`. No code yet; this is what the fixtures will implement once approved.

## 0. Core idea: mule behavior, not complaints

A money-mule account is recognised by **how money moves through it**, not by reports against it. (If complaints existed, the bank would already have locked the account.) The signals the system must derive from raw transactions:

| Behavior | Meaning |
|---|---|
| **Dwell time** | Time between money arriving and leaving the account. Mules forward within minutes; genuine accounts hold funds for hours to days. |
| **Retention** | Share of inflow still in the account after a window. Mules end near zero. |
| **Velocity** | Number of transactions in a short window. Mules show bursts. |
| **Fan-in / fan-out** | Many distinct senders in, few receivers out (collection), or the reverse (distribution). |
| **Multi-hop layering** | Funds move A → B → C → D with minutes between each hop, ending at an off-ramp account. |
| **Account age** | A supporting factor only; never evidence alone. |

Why this separates a mule from a genuine busy shop: both have many inbound payments. A shop holds the money (long dwell, high retention, outflows on its own schedule). A mule passes it on (minutes, near-zero retention, chained).

Conventions
- Ids are deterministic and identical in Firestore and Neo4j. `now` is an injectable clock. Timestamps have minute precision.
- Currency INR. Everything is fictional and simulated.
- No stored fraud label, score, complaint, verdict, or scenario label. The "intended outcome" column in section 7 is what tests will assert, never something stored.
- `RiskSignal` nodes are **not seeded**. They are produced by agents at assessment time (for example `RAPID_PASS_THROUGH`, `MULTI_HOP_LAYERING`, `FAN_IN_BURST`), carry `INFERRED` provenance, and link via `FLAGGED_FOR` to the transactions that support them.

## 1. Scenario catalogue

| # | Payer → Recipient, amount | Entity type | What it proves |
|---|---|---|---|
| S1 | Asha → Rahul (landlord), 2,500 | General customer | Routine payment matching history passes cleanly |
| S2 | Asha → Sharma General Store, 1,200 | Genuine shopkeeper | Many inbound payments, but money is held for days and retained: not flagged |
| S3 | Priya → Sharma General Store, 400 | Shopkeeper + low-activity payer | Thin payer history is not a risk signal |
| S4 | Priya → Ananya (friend), 600 | Low-activity customer | Known recipient, tiny history: passes |
| S5 | Asha → Green Leaf Bakery, 450 | Genuine new business | A young account alone is not fraud |
| S6 | Asha → Heritage Jewellers, 40,000 | Anomaly only | Large deviation from her history, clean recipient: anomaly agent fires, network agent does not; questions, no hold |
| S7 | Asha → Spice Garden Restaurant, 1,800 | Hard false-positive | High daily pass-through to the owner, but long dwell, single hop, regular schedule: not a mule |
| S8 | Asha → Nova Trade Desk, 25,000 | Mule network (entry account) | Minutes of dwell, near-zero retention, 3-hop layering, high velocity. Outcome depends on questionnaire answers |
| S9 | Priya → Nova Trade Desk, 8,000 | Vulnerable payer + mule network | Thin history does not hide the network behavior |
| S10 | Asha → Quick Returns Hub, 5,000 | Mule network (mid-chain) | Another account in the same chain is detected from its own behavior, with no name or label to rely on |

## 2. Entities

### Customers (demo personas marked ★)

| id | Name | Role | Balance |
|---|---|---|---|
| `cust_asha` ★ | Asha Menon | General customer, 9 transactions | 84,250 |
| `cust_priya` ★ | Priya Nair | Low-activity, 2 transactions | 12,400 |
| `cust_s01` … `cust_s12` | Shopper 1 … 12 | Pay shops and businesses | 0 |
| `cust_p01` … `cust_p08` | Karan S., Meera P., Imran K., Divya R., Rohit M., Sana A., Vikram T., Neha B. | Pay into the mule network | 0 |

### Beneficiaries

| id | Name | Handle | First seen |
|---|---|---|---|
| `ben_rahul` | Rahul Verma | rahul.verma@trustpay | 400 d |
| `ben_freshmart` | Fresh Mart Grocers | freshmart@trustpay | 300 d |
| `ben_citypower` | City Power Board | citypower@trustpay | 500 d |
| `ben_metrocafe` | Metro Cafe | metrocafe@trustpay | 200 d |
| `ben_ananya` | Ananya Rao | ananya.rao@trustpay | 20 d |
| `ben_sharma_store` | Sharma General Store | sharma.store@trustpay | 700 d |
| `ben_wholesale_hub` | Wholesale Hub | wholesale.hub@trustpay | 900 d |
| `ben_greenleaf` | Green Leaf Bakery | greenleaf.bakery@trustpay | 25 d |
| `ben_heritage` | Heritage Jewellers | heritage.jewellers@trustpay | 600 d |
| `ben_spice_garden` | Spice Garden Restaurant | spice.garden@trustpay | 500 d |
| `ben_spice_owner` | Spice Garden (owner account) | spice.owner@trustpay | 500 d |
| `ben_novatrade` | Nova Trade Desk | nova.trade@trustpay | 3 d |
| `ben_quickreturns` | Quick Returns Hub | quick.returns@trustpay | 6 d |
| `ben_taskrewards` | Task Rewards Desk | task.rewards@trustpay | 11 d |
| `ben_swiftassist` | Swift Assist Services | swift.assist@trustpay | 9 d |

No complaint counts or flags exist on any entity.

### Accounts

One per customer and beneficiary: `acct_<id without prefix>` (for example `acct_asha`, `acct_novatrade`), `openedAt` equal to the owner's first-seen date, `OWNS` 1:1.

## 3. Transactions

Each has exactly one `SENT` (source account) and one `PAID` (beneficiary). All are `COMPLETED` history. The scenario payments S1–S10 are created live and are not seeded.

### 3.1 Asha Menon: 9 transactions (baseline)

| id | To | Amount | Note | Days ago |
|---|---|---|---|---|
| `txn_hist_1` | `ben_rahul` | 2,500 | September rent | 43 |
| `txn_hist_2` | `ben_rahul` | 2,500 | August rent | 74 |
| `txn_hist_3` | `ben_rahul` | 2,500 | July rent | 104 |
| `txn_hist_4` | `ben_freshmart` | 1,850 | Groceries | 5 |
| `txn_hist_5` | `ben_freshmart` | 1,240 | Groceries | 19 |
| `txn_hist_6` | `ben_freshmart` | 2,100 | Groceries | 33 |
| `txn_hist_7` | `ben_citypower` | 1,960 | Electricity bill | 12 |
| `txn_hist_8` | `ben_metrocafe` | 480 | Lunch | 2 |
| `txn_hist_9` | `ben_metrocafe` | 360 | Coffee | 9 |

Baseline: average ≈ 1,721, maximum 2,500, 4 usual recipients.

### 3.2 Priya Nair: 2 transactions

| id | To | Amount | Note | Days ago |
|---|---|---|---|---|
| `txn_priya_1` | `ben_ananya` | 1,200 | Shared dinner | 20 |
| `txn_priya_2` | `ben_metrocafe` | 300 | Coffee | 8 |

### 3.3 Sharma General Store (genuine, high volume, money held)

Inbound: 120 transactions `txn_shop_001` … `txn_shop_120`, for i = 1..120 (deterministic):
- sender `cust_s{((i-1) mod 12)+1}`
- day offset `1 + round((i-1) × 59 / 119)` days ago; time of day `10:00 + ((i × 37) mod 600)` minutes (business hours)
- amount `80 + ((i × 379) mod 1721)`, note "Store purchase"

Outbound: `ben_sharma_store` → `ben_wholesale_hub`, 8 weekly supplier payments `txn_shop_out_1..8` of ₹6,000, at 10:00, 3, 10, 17, 24, 31, 38, 45, 52 days ago.

Resulting behavior: about 2 payments a day, roughly ₹113k inflow, ₹48k outflow, so about 57% retained. Funds sit for days before any outflow, and outflows are on a weekly schedule unrelated to individual payments.

### 3.4 Green Leaf Bakery (genuine new business)

8 inbound `txn_leaf_1..8`, i = 1..8:
- senders `cust_s01` … `cust_s06`, then `cust_s01`, `cust_s02`
- days ago 1, 3, 5, 8, 11, 14, 18, 23 (midday)
- amount `150 + ((i × 137) mod 751)`
- no outbound

Young but low volume, no outflow, 100% retained.

### 3.5 Heritage Jewellers (established, high ticket)

20 inbound `txn_jewel_1..20`, i = 1..20:
- sender `cust_s{((i-1) mod 12)+1}`, days ago `4 × i`
- amount `5,000 + ((i × 7919) mod 55,001)`, note "Jewellery purchase"
- no outbound

Makes a ₹40,000 payment to an established merchant plausible.

### 3.6 Spice Garden Restaurant (high pass-through, but not a mule)

For each of the last 20 days (d = 1..20):
- 3 inbound payments at 12:30, 15:30, 20:00 from `cust_s{...}` (cycling through the 12 shoppers), amount `200 + ((i × 313) mod 1301)` with i counting inbound payments 1..60 (`txn_spice_in_1..60`)
- 1 outbound sweep from `ben_spice_garden` to `ben_spice_owner` at 23:00, 95% of that day's inbound total, rounded (`txn_spice_out_1..20`)

Resulting behavior: about 95% pass-through, but dwell is 3 to 10 hours, only one hop (the owner's account forwards nothing), at exactly the same time every day, and the account is 500 days old. This is the case that proves "money going out" alone is not the signal.

### 3.7 Mule network: collection, layering, off-ramp

Chain: victims → `ben_novatrade` (entry) → `ben_quickreturns` → `ben_taskrewards` → `ben_swiftassist` (off-ramp, no onward transfers).

For k = 1..8, victim `cust_p0k` pays in, then funds are forwarded hop by hop:

| k | Victim | Inbound amount | Hours ago (inbound) |
|---|---|---|---|
| 1 | `cust_p01` | 8,000 | 70 |
| 2 | `cust_p02` | 12,000 | 60 |
| 3 | `cust_p03` | 5,000 | 50 |
| 4 | `cust_p04` | 9,500 | 41 |
| 5 | `cust_p05` | 6,000 | 30 |
| 6 | `cust_p06` | 15,000 | 22 |
| 7 | `cust_p07` | 7,000 | 12 |
| 8 | `cust_p08` | 11,000 | 5 |

Forwards for each k (all `COMPLETED`):
- hop 1: `ben_novatrade` → `ben_quickreturns`, 98% of inbound, **6 minutes** after arrival
- hop 2: `ben_quickreturns` → `ben_taskrewards`, 97%, **4 minutes** after hop 1
- hop 3: `ben_taskrewards` → `ben_swiftassist`, 96%, **5 minutes** after hop 2

Ids: `net_in_k`, `net_h1_k`, `net_h2_k`, `net_h3_k` (32 transactions). Each account keeps only 1 to 2% as a fee, so balances stay near zero.

Raw facts queries must be able to compute (asserted in tests, never stored):
- `ben_novatrade`: 8 distinct senders in 70 h, median dwell about 6 min, retention about 2%, one onward destination.
- Layering: a 3-hop chain with each hop under 15 min, ending at an account with no onward transfers.
- Velocity: 32 transactions across 4 accounts within 70 h.
- Account ages: 3, 6, 11, 9 days (supporting only).

## 4. Connections (`CONNECTED_TO`)

Stored, `VERIFIED_SYNTHETIC`, bidirectional.

| Between | Kind | Meaning |
|---|---|---|
| `acct_sharma_store` ↔ `acct_wholesale_hub` | `BUSINESS_SUPPLIER` | Declared supplier relationship |
| `acct_spice_garden` ↔ `acct_spice_owner` | `SAME_OWNER` | Declared business and owner accounts |

No stored connection exists between any mule accounts. Their relationship is visible only through the transfers, so the evidence is behavioral (`INFERRED`).

`SAME_OWNER` is a new kind added to the schema (`SHARED_DEVICE`, `BUSINESS_SUPPLIER`, `SAME_OWNER`).

## 5. Risk signals

None seeded. See section 0.

## 6. Summary counts

| Item | Count |
|---|---|
| Customers | 22 |
| Beneficiaries | 15 |
| Accounts | 37 |
| Seeded transactions | 9 + 2 + 128 + 8 + 20 + 80 + 32 = 279 |
| `CONNECTED_TO` | 2 stored pairs |
| `FLAGGED_FOR` / `RiskSignal` | 0 seeded |

## 7. Intended outcomes (tests, not data)

| # | Evidence the queries and agents should find | Intended result |
|---|---|---|
| S1 | Known recipient, amount in range | Proceed |
| S2 | 12 senders, dwell of days, about 57% retained, weekly scheduled outflow | Proceed |
| S3 | Same recipient; payer history thin | Proceed |
| S4 | Known recipient | Proceed |
| S5 | Young, low volume, no outflow, fully retained | Proceed |
| S6 | Amount about 16× her maximum; recipient established, no pass-through | Review with questions; no hold |
| S7 | 95% pass-through but 3 to 10 h dwell, single hop, daily schedule, 500 days old, declared owner link | Proceed |
| S8 | Amount deviation; minutes of dwell, about 2% retention, 3-hop layering, 8 senders, high velocity: at least two independent behaviors | Review with benign answers; Hold with scam answers |
| S9 | Same network behavior; modest amount; thin history gives low-confidence anomaly | Review with benign answers; Hold with scam answers |
| S10 | Mid-chain account: short dwell, near-zero retention, forwards to `ben_taskrewards`, receives from `ben_novatrade` | Elevated; questions; Review with benign answers, Hold with scam answers |

## 8. Decisions (resolved)

1. Behavior set stays: dwell time, retention, velocity, fan-in, multi-hop layering with an off-ramp; account age is supporting only.
2. Spice Garden Restaurant (S7) stays as the hard false positive.
3. Risk is always computed by the agents. Only data is stored; no risk signals are seeded.
4. Scope stays on the main use cases: one mule chain, no second network shape.
5. Shop and victim payers are `Customer` nodes (`cust_s*`, `cust_p*`) because every sender in the graph needs an account to send from; this has no effect on the demo, where only Asha and Priya are selectable personas.
6. `knowledge-graph`, `risk-policy`, `agent-orchestration`, `investigation-console`, `integration-testing`, `proposal` and `tasks` are updated to match this document.
