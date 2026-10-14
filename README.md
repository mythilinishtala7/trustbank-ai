# TrustBank AI

Agentic fraud prevention **before payment authorization**. A simulated payment flow where a knowledge graph and real Google ADK agents (on Gemini) assess the recipient and the transaction, ask contextual questions, and apply a simulated 3-minute hold when the policy requires it.

All data is synthetic. Payments and PIN entry are simulated; no real money or credentials are involved. The agents, graph queries and Gemini calls are real.

## How it works

```
Angular (customer app  +  /investigation console)
              │
        FastAPI backend ── dummy customer entry, investigator access code
              │
   Orchestrator (Google ADK)
     ├─ Anomaly agent          deterministic, uses customer history
     ├─ Fraud-network agent    deterministic, uses Neo4j graph queries
     ├─ Questionnaire agent    Gemini
     └─ Explainer agent        Gemini
              │
   Deterministic risk policy ── proceed · review · hold · cancel
              │
     Neo4j (graph)      Firestore (system of record)
```

- Agents produce evidence and recommendations; the deterministic policy and payment service own every state transition.
- A graph connection is evidence to investigate, not proof of guilt. A new recipient or limited history is never high risk on its own.
- A hold never auto-releases when the timer expires; the customer must cancel or confirm independent verification.

### Two experiences

| | Customer app (`/`) | Investigation console (`/investigation`) |
|---|---|---|
| Audience | Customer | Demo presenter / judges |
| Entry | Pick a demo persona (no credentials) | Demo access code, enforced by the backend |
| Shows | Payment flow, clear warning, questions, hold, cancel | Live agent timeline, graph, evidence, policy decision |
| Never shows | Agent names, risk scores, graph, traces | n/a |

Search the same `txn_` reference in the console to see how the agents reached the decision.

### Synthetic scenarios

| Scenario | Purpose |
|---|---|
| Genuine shopkeeper | High-volume legitimate activity is not flagged |
| Fraudulent beneficiary network | Risk found from graph behavior and independent signals |
| Normal low-activity account | Limited history is not evidence of fraud |
| General customer | Deviations from individual behavior are detected |

Outcomes are never hardcoded; the agents compute them from the data.

## Specification

The OpenSpec change is the source of truth: `openspec/changes/trustbank-agentic-fraud-prevention/`

| File | Contents |
|---|---|
| `proposal.md` | Why, scope, stack, success criteria |
| `design.md` | Architecture, data split, contracts, failure handling |
| `tasks.md` | Implementation slices 0–7 |
| `specs/knowledge-graph` | Neo4j schema, provenance, fixtures, queries |
| `specs/agent-orchestration` | Agents, contracts, orchestrator |
| `specs/risk-policy` | Scoring, thresholds, payment state machine |
| `specs/backend-api` | API endpoints and response models |
| `specs/access-control` | Dummy entry and investigator access |
| `specs/customer-experience` | Customer payment journey |
| `specs/investigation-console` | Console behavior |
| `specs/integration-testing` | Test layers and scenario acceptance |

Appeals and full user accounts are deferred (not in the MVP).

## Working with the spec

1. Read the proposal and design, then pick the next unchecked task in `tasks.md`.
2. Implement one task at a time, with tests; stop for review after each.
3. Tick the task off and keep the change folder until acceptance checks pass.

Guidance for Copilot: `COPILOT_INSTRUCTIONS.md`.

## Stack

| Layer | Choice |
|---|---|
| Frontend | Angular |
| Backend | Python, FastAPI |
| Agents | Google ADK (Python) |
| Model | Gemini via Vertex AI |
| Graph | Neo4j |
| System of record | Firestore |
| Hosting | Cloud Run (API), Firebase Hosting (web) |

## Status

The specification is complete and committed. Implementation starts with slice 1 (synthetic data and knowledge graph).

`apps/banking-web` and `services/{fraud-api,agents}` are the earlier TypeScript prototype. They are kept as reference for fixture values and are removed once the Python backend reaches parity (task 7.3). Their old run instructions no longer apply.

## Guardrails

- All customers, accounts, transfers, risk indicators and outcomes are synthetic.
- No real banking integration, money movement or PIN collection.
- Free-text customer answers are untrusted input and never alter policy directly.
- Do not claim the prototype has proven real-world fraud reduction.
