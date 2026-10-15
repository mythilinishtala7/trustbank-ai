# Capability: Backend API

Python FastAPI service in `services/backend`. Two audiences with separate response models.

## Requirements

### Requirement: REST API
Endpoints under `/api/v1`, with an OpenAPI document generated from Pydantic models.

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/health` | none | Firestore, Neo4j, and model reachability |
| GET | `/personas` | none | Demo personas available for dummy entry |
| POST | `/auth/customer` | none | Dummy entry: persona id → customer token |
| POST | `/auth/investigator` | none | Access code → investigator token |
| GET | `/me` | customer | Name, balance, recent transactions |
| GET | `/recipients/lookup?q=` | customer | Resolve UPI id or account number |
| POST | `/payments` | customer | Create and assess a payment (requires `Idempotency-Key`) |
| GET | `/payments/{id}` | customer (owner) | Customer view of the payment |
| POST | `/payments/{id}/answers` | customer (owner) | Submit scam-check answers |
| POST | `/payments/{id}/acknowledge` | customer (owner) | Acknowledge a REVIEW warning |
| POST | `/payments/{id}/verify` | customer (owner) | Confirm independent verification after hold expiry |
| POST | `/payments/{id}/continue` | customer (owner) | Move to authorization when allowed |
| POST | `/payments/{id}/authorize` | customer (owner) | Demo PIN authorization |
| POST | `/payments/{id}/cancel` | customer (owner) | Cancel |
| GET | `/investigation/transactions/{id}` | investigator | Transaction, assessments, bounded graph |
| GET | `/investigation/transactions/{id}/events` | investigator | Live agent execution events (SSE) |
| GET | `/investigation/transactions/{id}/timeline` | investigator | Stored timeline (polling fallback) |

#### Scenario: Error format
- WHEN a request fails
- THEN the response SHALL be `{ "error": { "code": string, "message": string, "requestId": string } }` with status 400, 401, 403, 404, 409, 422, 429, or 503
- AND internal details SHALL NOT be leaked

### Requirement: Separate response models
Customer endpoints SHALL return whitelisted customer models only (see `customer-experience`). Detailed assessments, scores, agent traces, and graph data SHALL be served only by `/investigation/*`.

#### Scenario: Customer model is a whitelist
- THEN a test SHALL fail if any customer response contains a field outside the whitelist

### Requirement: Transaction reference
Each payment SHALL be assigned a transaction reference at creation (`txn_<id>`), which becomes the transaction id on completion. The investigation lookup SHALL resolve both payment references and historical transaction ids.

### Requirement: Trace retention
The backend SHALL persist the agent trace events for every payment regardless of whether any console is open.

### Requirement: Payment lifecycle enforcement
The backend SHALL enforce the state machine in `risk-policy`; invalid transitions return 409.

#### Scenario: Authorization without clearance
- GIVEN a payment not in `READY_FOR_AUTH`
- WHEN `/authorize` is called
- THEN the server SHALL reject it with 409

### Requirement: Idempotency and concurrency
- `POST /payments` with the same `Idempotency-Key` and customer SHALL return the original payment.
- State transitions SHALL run inside a Firestore transaction on the payment document.

### Requirement: Dummy PIN
`/authorize` SHALL accept a 4–6 digit demo PIN, validate its format only, never store or log it, and label receipts as simulated.

### Requirement: Configuration
All settings (thresholds, weights, hold seconds, model name, project ids, Neo4j URI, token secret, investigator code) SHALL come from environment variables validated at startup. The service SHALL refuse to start with missing required values.

### Requirement: Timeouts and resilience
Per-agent timeouts (detectors 8 s, Gemini 15 s by default). Failure behavior SHALL follow `design.md`.

### Requirement: Observability
Requests SHALL carry a request id in logs and responses. Logs SHALL NOT contain PINs, tokens, the access code, or customer free text.

### Requirement: Deployability
The backend SHALL run in a container on Cloud Run with Application Default Credentials, and locally via documented commands plus `docker compose` for Neo4j and the Firestore emulator.
