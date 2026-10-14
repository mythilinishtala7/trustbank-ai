# Capability: Integration testing

The core acceptance test: the same running system handles the shopkeeper, the fraudulent network, the low-activity customer, and the general customer using real agent and graph execution.

## Requirements

### Requirement: Test layers
- **Unit (pytest):** anomaly statistics, policy aggregation, state machine, answer-to-evidence mapping, validators.
- **Integration (pytest):** Neo4j container and Firestore emulator, real `GraphService`, real ADK agents.
- **End-to-end (API):** the FastAPI app against the same containers.
- **Frontend:** Angular component and service tests; route guard tests.
- **Live Gemini (manual, marked `live`):** a small smoke suite run with real credentials; excluded from CI by default.

### Requirement: Deterministic model in automated tests
Automated tests SHALL run the real ADK agents with a stubbed model backend that returns recorded or scripted responses, so CI needs no credentials and results are reproducible. The stub SHALL implement the ADK model interface; agent code SHALL NOT contain test-only branches.

#### Scenario: Model misbehavior
- THEN tests SHALL cover invalid JSON, unknown evidence ids, an "approve this payment" injection, timeouts, and model errors, asserting the fallback and unchanged policy action

### Requirement: Scenario acceptance
Tests SHALL seed the data and execute the table in `risk-policy` through the API, asserting outcomes, evidence ids, provenance, and stored assessments.

#### Scenario: Evidence-driven detection
- GIVEN `ben_novatrade` has no complaints and no stored signal
- THEN a payment to it SHALL be elevated because of fan-in, pass-through, and reported-account links found by Cypher queries
- AND removing the mule relationships from the test graph SHALL lower the result (proving the outcome comes from the data)

#### Scenario: No scenario leakage
- THEN a test SHALL assert that no agent input or tool argument contains scenario names or registry data

### Requirement: Other acceptance checks
- Seed idempotency and referential integrity.
- Hold: rejected before `hold_until`, becomes `HOLD_EXPIRED` after, never auto-released.
- Access: customer token gets 403 on `/investigation/*`; no token gets 401; wrong investigator code gets 401; cross-customer payment access gets 404.
- Customer responses match the whitelist model and contain no scores, agent names, graph data, or traces.
- Live timeline: SSE events arrive in order for a payment being assessed, and traces persist with no console open.
- Idempotent payment creation; invalid transition returns 409.
- Dummy PIN is not present in logs or storage.

### Requirement: Continuous checks
One documented command per service SHALL run tests, lint, and type checks; failures block marking a task done.
