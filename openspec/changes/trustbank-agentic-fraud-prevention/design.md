# Design: TrustBank AI

## Principles

1. **Evidence before alarm.** Explain concrete signals; association is evidence to investigate, never proof of guilt.
2. **Agents advise, the backend decides.** Agents return structured findings. Only the payment service changes state.
3. **Real execution, synthetic data.** No hardcoded outcomes per scenario; no scenario label is visible to agents.
4. **Quiet protection.** Low-risk payments stay simple.
5. **Use an LLM only where language is the task.** Statistical and graph detection are deterministic algorithms exposed as tools.
6. **Fail safe.** A failed agent never silently lowers risk.

## Architecture

```
Angular (customer app at /, investigation console at /investigation)
        │ HTTPS + signed session token
FastAPI backend ── auth/RBAC · payment service (state machine) · API
        │
Orchestrator (ADK) ── Parallel[ Anomaly agent, Fraud network agent ] → (if elevated) Questionnaire agent
        │                                                                 Explainer agent (customer text)
Risk policy (pure Python) ── aggregate · final action · hold
        │
Neo4j (graph, Cypher)          Firestore (system of record + app data)
```

### Repository layout (target)

- `apps/banking-web`: Angular; `/` customer routes, `/investigation` is a lazy-loaded separate shell behind an access-code gate.
- `services/backend`: Python package `trustbank` (`api/`, `auth/`, `payments/`, `policy/`, `agents/`, `graph/`, `repos/`, `seed/`), `pyproject.toml`, `tests/`.
- `infra/`: `docker-compose.yml` (Neo4j), Firestore emulator config, `firestore.rules`, `firestore.indexes.json`.
- Existing TypeScript `services/fraud-api` and `services/agents` are superseded and removed in the cleanup slice, not before the Python backend reaches parity.

## Data stores

**Firestore (system of record).** Collections: `customers`, `accounts`, `beneficiaries`, `transactions`, `payments` (with `events` subcollection), `assessments` (append-only), `audit_log`. Document ids equal graph ids. Clients never access Firestore; `firestore.rules` deny all.

**Neo4j (knowledge graph).** A projection of Firestore built by an ingestion job and updated when a payment completes. Labels `Customer`, `Account`, `Transaction`, `Beneficiary`, `RiskSignal`; relationships `OWNS`, `SENT`, `PAID`, `CONNECTED_TO`, `FLAGGED_FOR`. Uniqueness constraints on `id`. Details in `specs/knowledge-graph`.

**Provenance** on all evidence: `VERIFIED_SYNTHETIC` (declared intelligence), `INFERRED` (query-time graph or statistical finding), `USER_PROVIDED` (customer answers).

## Where Gemini is used

| Component | Technology | Why |
|---|---|---|
| Anomaly agent | ADK custom (non-LLM) agent + statistical tools | Reproducible and explainable |
| Fraud network agent | ADK custom (non-LLM) agent + Cypher tools | Graph facts must be exact |
| Questionnaire agent | ADK `LlmAgent`, Gemini | Contextual question wording, classify optional free-text answers |
| Explainer agent | ADK `LlmAgent`, Gemini | Plain-language, evidence-grounded customer text |
| Orchestrator | ADK workflow agent (`ParallelAgent` + custom conditional step) | Execution order and result collection |
| Risk policy | Python | Deterministic decision |

LLM agents use structured output schemas, receive only structured evidence (never raw scenario ids or raw free text except the single free-text answer field, treated as untrusted data), and their output is validated (schema, allowed enums, evidence-id grounding). Details in `specs/agent-orchestration`.

## Contracts to freeze first

1. Graph schema and ids (`specs/knowledge-graph`).
2. `AgentFinding`, `Evidence`, `Question`, `Answer`, `Explanation` (`specs/agent-orchestration`).
3. `Assessment`, `Payment`, state machine (`specs/risk-policy`).
4. REST API and error format (`specs/backend-api`).

Implement them as Pydantic models with an exported OpenAPI document; the Angular models are **mirrored by hand** from it (decision, task 0.4). `services/backend/openapi.json` is the committed contract and `test_openapi.py` fails if it drifts from the code; customer models in `apps/banking-web/src/app/core/models.ts` deliberately omit scores, agent names, graph data and traces, so they are a whitelist rather than a full generated client.

## Risk policy summary (defaults, configurable)

- Detectors return scores 0–100 with confidence. `pre_score = round(0.4 × anomaly + 0.6 × network)`.
- `pre_score ≥ 30` (elevated) invokes the questionnaire agent.
- Final score adds bounded context points from answers. LOW < 30, MEDIUM 30–59 → `REVIEW`, HIGH ≥ 60 → `HOLD`.
- Evidence cap: without network evidence, the score stays below HIGH unless context points alone reach 40.
- Thresholds, weights, and hold seconds (default 180) live in one config object, stored with each assessment.

## Payment state machine (summary)

`INITIATED → ASSESSING → READY_FOR_AUTH` (LOW) or `→ QUESTIONNAIRE → {READY_FOR_AUTH | REVIEW | HOLD_ACTIVE}`; `REVIEW → READY_FOR_AUTH` after acknowledgement; `HOLD_ACTIVE → HOLD_EXPIRED` on timer; `HOLD_EXPIRED` waits for an explicit customer action (cancel, or continue after confirming independent verification); terminal `COMPLETED`, `CANCELLED`. Full transitions in `specs/risk-policy`.

## UX direction

Calm, light fintech; navy `#14243A`, blue `#2864E8`, off-white `#F7F8FA`, muted `#697586`, amber `#D99116`, red `#D92D20` only for high-risk interventions. One primary action per screen. The investigation console is a distinct shell, begins with a transaction-ID search, and shows only a bounded neighborhood. The customer app never shows agent names, scores, graph, or traces.

## Security and privacy

- No user accounts or passwords. Customers enter as demo personas; the investigation console requires a demo access code from server configuration. Session tokens are signed with a server secret; no secrets committed.
- Dummy PIN: format-checked, never stored or logged.
- Free text from customers is untrusted: length-limited, never interpolated into instructions, only passed as quoted data to a schema-constrained classifier.
- All Cypher is parameterized.
- Logs carry request ids and ids only; no PIN, no free text.
- Investigation endpoints are enforced server-side by role; hiding a route is not access control. Customer responses are whitelisted models.

## Failure handling

| Failure | Behavior |
|---|---|
| Detector error or timeout | Recorded in trace; assessment marked `INCOMPLETE`; policy treats missing evidence conservatively (never LOW because of a failure; routes to `REVIEW`) |
| Gemini error or invalid output (questionnaire) | Degraded mode: fixed allow-listed question set tied to present signals; recorded in trace |
| Gemini error or invalid output (explainer) | Template explanation built from evidence summaries; recorded in trace |
| Neo4j unavailable | Assessment fails safe to `REVIEW`; error recorded; health endpoint reports degraded |
| Firestore write conflict | Transactional retry; idempotency keys prevent duplicate payments |

## Observability

Structured logs, a per-assessment decision trace stored in Firestore, `/health` reporting Firestore, Neo4j, and model reachability.
