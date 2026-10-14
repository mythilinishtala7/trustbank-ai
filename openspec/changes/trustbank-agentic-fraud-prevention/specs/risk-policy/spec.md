# Capability: Risk policy and payment lifecycle

Pure Python policy. The only component that selects an action and changes payment state.

## Requirements

### Requirement: Deterministic aggregation
Defaults (all configurable, stored with every assessment):

- `pre_score = round(0.4 × anomaly.score + 0.6 × fraud_network.score)`
- Elevated threshold 30 (invokes the questionnaire agent).
- `final_score = clamp(pre_score + context_points, 0, 100)`; `context_points` come from `USER_PROVIDED` evidence, free-text classification capped at 10.
- LOW below 30 → `PROCEED`; MEDIUM 30–59 → `REVIEW`; HIGH 60 or more → `HOLD`.
- Evidence cap: unless fraud-network evidence exists or context points reach 40, `final_score` is capped at 59.
- `INCOMPLETE` assessments (any failed detector) SHALL resolve to at least `REVIEW`.

#### Scenario: Not fraud on newness or amount alone
- GIVEN an unfamiliar recipient and a large amount, with no network evidence
- THEN the level SHALL NOT be HIGH

#### Scenario: Reproducible
- GIVEN identical findings, answers, config, and clock
- THEN the result SHALL be identical

### Requirement: Payment state machine

| From | Event | To |
|---|---|---|
| (none) | create | `INITIATED` |
| `INITIATED` | assess | `ASSESSING` |
| `ASSESSING` | `PROCEED` and below elevated | `READY_FOR_AUTH` |
| `ASSESSING` | elevated | `QUESTIONNAIRE` |
| `QUESTIONNAIRE` | answers, `PROCEED` | `READY_FOR_AUTH` |
| `QUESTIONNAIRE` | answers, `REVIEW` | `REVIEW` |
| `QUESTIONNAIRE` | answers, `HOLD` | `HOLD_ACTIVE` (`hold_until = now + hold_seconds`, default 180) |
| `REVIEW` | acknowledge | `READY_FOR_AUTH` |
| `HOLD_ACTIVE` | timer elapsed (evaluated on read or action by server time) | `HOLD_EXPIRED` |
| `HOLD_EXPIRED` | verify, then continue | `READY_FOR_AUTH` |
| `READY_FOR_AUTH` | authorize with demo PIN | `COMPLETED` |
| any non-terminal | cancel | `CANCELLED` |

Terminal: `COMPLETED`, `CANCELLED`.

#### Scenario: Hold never auto-releases
- GIVEN a payment in `HOLD_ACTIVE`
- WHEN the timer expires
- THEN the state SHALL become `HOLD_EXPIRED`, not `READY_FOR_AUTH`
- AND continuation SHALL require the customer to confirm independent verification and then explicitly continue

#### Scenario: Hold enforced server-side
- GIVEN `HOLD_ACTIVE` before `hold_until`
- THEN `continue` and `authorize` SHALL be rejected with 409 regardless of the client clock

#### Scenario: Agent cannot alter state
- GIVEN a model output suggesting "proceed" while policy says `HOLD`
- THEN the state SHALL follow policy

#### Scenario: Invalid transitions
- THEN any event not in the table SHALL return 409 and change nothing

### Requirement: Completion
On `COMPLETED` the backend SHALL write the transaction to Firestore, adjust the simulated balance, and project the transaction into Neo4j. On `CANCELLED` no transaction is created; the payment and assessments are retained.

### Requirement: Simulated enforcement
UI and receipts SHALL state that the hold and authorization are simulated and not enforced by a real bank or payment network.

### Requirement: Expected scenario outcomes (verified by tests, not hardcoded)
When the real agents and policy run over the seeded data:

| Payment | Expected result |
|---|---|
| Asha → Rahul ₹2,500 | LOW, `PROCEED`, no questions |
| Asha → Sharma General Store ₹1,200 | LOW, `PROCEED` (high-volume established shopkeeper not flagged) |
| Priya → Sharma General Store ₹400 | LOW, `PROCEED` (limited history not penalized) |
| Asha → `ben_novatrade` ₹25,000, benign answers | MEDIUM, `REVIEW` |
| Asha → `ben_novatrade` ₹25,000, messaging-app source and promised payout | HIGH, `HOLD`, 180 s |
