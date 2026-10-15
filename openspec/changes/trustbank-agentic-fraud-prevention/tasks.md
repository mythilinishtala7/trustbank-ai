# Tasks

One slice at a time. A task is done only when its acceptance criteria pass and lint/type checks for the touched service pass. Automated tests are out of scope; verify by running the real flow. Stop for review after each task.

## 0. Contracts and repository setup

- [ ] 0.1 Review and approve all specs; freeze graph schema, scenario ids, `AgentFinding`/`Evidence`/`Question`/`Answer`, `Assessment`/`Payment`, state machine, and API paths.
- [x] 0.2 Scaffold `services/backend` (Python 3.12 target; 3.14 locally, FastAPI, pydantic v2, pytest, ruff, mypy, `pyproject.toml`); health endpoint; config validation.
- [x] 0.3 Add `infra/docker-compose.yml` (Neo4j 5, Firestore emulator), `firestore.rules` (deny all), `firestore.indexes.json`, `.env.example`; document how to start.
- [ ] 0.4 Export the OpenAPI document and decide how Angular models are generated or mirrored.

## 1. Slice 1 — Synthetic data and knowledge graph (current focus)

Spec: `specs/knowledge-graph`.

- [x] 1.1 Define Pydantic models for Firestore documents (customers, accounts, beneficiaries, transactions) and graph nodes/relationships with provenance.
- [x] 1.2 Create deterministic fixture generators for the four scenarios, with an injectable clock and a tests-only scenario registry.
- [x] 1.3 Implement Firestore repositories and the seed command (deterministic ids, batched, idempotent, reset option).
- [x] 1.4 Implement Neo4j constraints and the ingestion job (`MERGE`, idempotent); verify referential integrity.
- [x] 1.5 Implement `GraphService` queries: `get_node`, `neighbors`, `transaction_neighborhood`, `account_age_days`, `recent_senders`, `flow_profile` (dwell, retention, velocity), `forwarding_chain` (parameterized).
- [ ] 1.6 Document setup, seeding, and sample queries in the README.

## 2. Slice 2 — Backend foundation and access control

Specs: `backend-api`, `access-control`.

- [x] 2.1 Error format, request ids, structured logging without sensitive data.
- [x] 2.2 `/personas`, `/auth/customer` (dummy entry), `/auth/investigator` (access code from config, rate limited), signed tokens with expiry.
- [x] 2.3 Role dependencies; 401, 403, and cross-customer 404 responses.
- [x] 2.4 `/me` and `/recipients/lookup` with whitelisted customer response models.
- [x] 2.5 `/health` with Firestore, Neo4j, and model checks.

## 3. Slice 3 — Agents

Spec: `agent-orchestration`.

- [ ] 3.1 Pydantic contracts and validators (schema, evidence grounding, enums).
- [ ] 3.2 Anomaly agent (ADK custom agent) with statistical tools over Firestore history, including low-history confidence handling.
- [ ] 3.3 Fraud network agent (ADK custom agent) with Cypher tools and corroboration/established-account rules.
- [ ] 3.4 Questionnaire agent (`LlmAgent`) with structured output, fixed option sets, deterministic answer-to-evidence mapping, free-text classifier, prompt-injection defences.
- [ ] 3.5 Explainer agent (`LlmAgent`) with grounding validation and template fallback.
- [ ] 3.6 Orchestrator workflow (parallel detectors, conditional questionnaire), timeouts, failure and degraded handling.
- [ ] 3.7 Assessment record persistence (append-only) including tool-call trace.
- [ ] 3.8 Live Gemini smoke test (manual) on Vertex AI.

## 4. Slice 4 — Risk policy and payment lifecycle

Spec: `risk-policy`.

- [ ] 4.1 Config object and deterministic aggregation with evidence cap and `INCOMPLETE` handling.
- [ ] 4.2 Payment state machine with Firestore transactions and idempotency.
- [ ] 4.3 `/payments` create, get, answers, acknowledge, verify, continue, authorize (dummy PIN), cancel.
- [ ] 4.4 Server-enforced hold (`HOLD_ACTIVE`/`HOLD_EXPIRED`) with injectable clock.
- [ ] 4.5 Completion writes: Firestore transaction, balance, Neo4j projection.

## 5. Slice 5 — Customer experience

Spec: `customer-experience`.

- [ ] 5.1 API client, session service, route guards, shared design tokens.
- [ ] 5.2 Persona entry, minimal home, recent transactions.
- [ ] 5.3 Recipient, amount, and review screens.
- [ ] 5.4 Scam-check questions screen.
- [ ] 5.5 Review acknowledgement and hold screens with server-driven countdown and expiry flow.
- [ ] 5.6 Demo PIN and receipt; loading/error/empty states; accessibility and responsive pass.

## 6. Slice 6 — Investigation console

Specs: `investigation-console`, `access-control`.

- [ ] 6.1 `/investigation/transactions/{id}` and `/timeline` endpoints with audit log; trace events persisted for every payment.
- [ ] 6.2 SSE endpoint `/investigation/transactions/{id}/events` with polling fallback.
- [ ] 6.3 Console shell at `/investigation` with access-code gate and guard.
- [ ] 6.4 Transaction search, bounded Cytoscape graph with highlights, legend, node details.
- [ ] 6.5 Live agent timeline, evidence and policy panel with provenance badges.
- [ ] 6.6 Verify access control manually (including that customer responses expose no internal fields).

## 7. Slice 7 — Hardening and delivery

Spec: `integration-testing`.

- [ ] 7.1 Full scenario end-to-end run including model misbehavior cases and the "delay the forwarding transactions lowers the result" proof.
- [ ] 7.2 Container image and Cloud Run deployment; Secret Manager for credentials; Neo4j hosting decision documented.
- [ ] 7.3 Remove the superseded TypeScript `services/fraud-api` and `services/agents` after parity; update README and demo script.
- [ ] 7.4 Mobile/desktop visual pass and accessibility audit.

## Deferred (not in MVP)

- Appeals and investigator resolution.
- Full user accounts and passwords.
- Additional agents (for example cluster summarizer).
