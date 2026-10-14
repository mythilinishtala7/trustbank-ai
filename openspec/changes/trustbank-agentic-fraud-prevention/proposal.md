# Change: TrustBank AI — agentic fraud prevention before payment authorization

## Why

Customers can be manipulated into voluntarily paying scam recipients, so authentication alone does not stop the loss. A payment should be assessed before authorization using the recipient's relationships, transaction patterns, and behavioral signals, not the transaction in isolation. When risk is elevated, the system should ask targeted questions, explain its reasoning, apply a simulated hold. 

## What changes

A simulated banking application backed by a real backend, a Neo4j knowledge graph, and real Google ADK agents running on Gemini.

- **Knowledge graph:** customers, accounts, transactions, beneficiaries, and risk signals in Neo4j, queried live by the agents and the investigation console.
- **Multi-agent assessment:** anomaly agent, fraud network agent, questionnaire agent, and explainer agent, run by an orchestrator.
- **Deterministic risk policy:** aggregates agent evidence and owns every payment state transition.
- **Pre-authorization intervention:** contextual questions, explanation, simulated three-minute hold that never auto-releases, cancel, independent verification.
- **Customer experience:** a simple payment-flow app with dummy entry (persona picker, no credentials). It shows a clear warning and next steps, and never agent names, risk scores, graph, or traces.
- **Investigation console** (separate `/investigation` route, demo-only access code enforced by the backend): live agent execution timeline, knowledge graph, findings and evidence, policy evaluation, final decision.

## Stack (decided)

| Layer | Choice |
|---|---|
| Web | Angular (customer app and investigation console, one workspace) |
| Backend | Python, FastAPI |
| Agents | Google Agent Development Kit (Python) |
| Model | Gemini via Vertex AI (Gemini API key allowed in local development) |
| Graph | Neo4j (Cypher) |
| Application data | Google Cloud Firestore |
| Hosting | Cloud Run (API); existing Firebase Hosting for the web app |
| Specs and workflow | GitHub + OpenSpec |

## Real vs synthetic

| Real, executable | Synthetic |
|---|---|
| Backend API, auth, payment state machine | Customers, accounts, beneficiaries |
| ADK agents and tool calls | Transactions and the fraud network |
| Cypher queries on Neo4j | Reported intelligence (complaints, shared devices) |
| Gemini calls | Payments and PIN entry (simulated; no real money) |
| Risk aggregation policy | |

Scenario data is made up, but outcomes SHALL emerge from running the real agents and queries over it. Nothing in the data or code carries a pre-assigned verdict.

## Scenarios (acceptance data)

1. **Genuine shopkeeper:** established, high volume, many senders, no flagged links. Must not be flagged.
2. **Fraudulent beneficiary network:** new account with no complaints but fan-in, pass-through, and links to reported accounts. Must be detected from independent evidence.
3. **Normal low-activity customer:** few transactions. Limited history is not a signal.
4. **General customer:** history that supports baseline deviation detection.

## Out of scope

- An appeals workflow (deferred beyond the MVP; assessments are immutable so it can be added later without schema changes).
- Real bank, UPI, or payment-network integration; real money movement; real PINs or credentials.
- Claims of real-world fraud-reduction.
- Training a production ML model.
- An LLM deciding payment state.
- Any non-Google LLM or AI service.
- Offline mock agent provider (tests use a stubbed model; see `integration-testing`).

## Users

- **Customer:** pays, answers scam-check questions, cancels, verifies.
- **Demo presenter / judge (investigator):** looks up the same transaction in the console and sees how the agents reached the decision.

## Success criteria

- The same running system correctly handles the shopkeeper, the fraudulent network, the low-activity customer, and the general customer, with real agent and graph execution.
- Every decision has a stored, traceable evidence record.
- Decisions are reproducible for fixed data, clock, and model responses.
- Gemini cannot change a payment state or invent evidence.
- The customer UI stays simple; the investigation console starts from a transaction ID, not the whole network.

## Delivery

One slice at a time, each finished and verified before the next (see `tasks.md`). Slice 1 is data and the knowledge graph.
