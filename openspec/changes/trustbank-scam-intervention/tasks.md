# Tasks

## 1. Repository discovery and contracts

- [x] 1.1 Inspect the existing repository, framework, scripts, routing, styles, and test setup; record the actual stack in the implementation notes.
- [x] 1.2 Agree on typed models for customers, beneficiaries, transactions, risk assessments, graph nodes/edges, scam-check answers, and payment state.
- [x] 1.3 Agree on the demo scenario IDs and risk policy thresholds before parallel work begins.
- [x] 1.4 Add design tokens and shared UI primitives using existing project conventions.

## 2. Synthetic data and risk engine

- [x] 2.1 Create deterministic synthetic customer, beneficiary, transaction, and graph fixtures.
- [x] 2.2 Implement a risk engine that evaluates amount deviation, beneficiary familiarity, graph signals, and scam context as separate evidence items.
- [x] 2.3 Implement configurable risk thresholds and action mapping.
- [x] 2.4 Add deterministic scenario tests for LOW, REVIEW, and HIGH outcomes.
- [x] 2.5 Ensure a new beneficiary with no complaints can be flagged only when other evidence supports it.

## 3. Banking experience

- [x] 3.1 Build the home screen and recent transactions.
- [x] 3.2 Build payment method selection and beneficiary entry/validation.
- [x] 3.3 Build amount/note entry and transaction review.
- [x] 3.4 Connect payment initiation to the risk assessment service before the simulated authorization screen.
- [x] 3.5 Implement normal payment, cancellation, receipt, and history updates.
- [ ] 3.6 Add responsive layout, accessible form controls, loading states, and error states.

## 4. Scam intervention

- [x] 4.1 Build the screening state.
- [x] 4.2 Build a concise risk summary using only supplied evidence.
- [x] 4.3 Add the two contextual scam-check questions and typed answer categories.
- [x] 4.4 Recalculate the risk outcome after answers using deterministic policy code.
- [x] 4.5 Implement the simulated hold/review state with cancel and verification guidance.
- [x] 4.6 Ensure no PIN/authorization screen appears before the risk flow completes.
- [x] 4.7 Add deterministic fallback explanations when no external model is configured or model calls fail.

## 5. Fraud network dashboard

- [x] 5.1 Build a separate investigator dashboard with graph canvas, legend, and minimal summary.
- [x] 5.2 Render synthetic customer and beneficiary nodes with directed transfer edges.
- [x] 5.3 Add node selection and a side panel with evidence and transaction history.
- [x] 5.4 Add graph navigation controls and empty/error states.
- [x] 5.5 Verify the network scenario is consistent with the risk engine's beneficiary identifiers and signals.

## 6. AI explanation integration

- [x] 6.1 Define a narrow interface for question selection and evidence explanation.
- [x] 6.2 Implement a deterministic mock-agent provider.
- [x] 6.3 If an external model is used, call it through a server-side adapter and pass only necessary synthetic context.
- [x] 6.4 Validate outputs and fall back to deterministic text when output is invalid or unavailable.
- [x] 6.5 Ensure the model cannot override risk actions or invent evidence.

## 7. Integration and demo readiness

- [x] 7.1 Integrate the normal, suspicious-job, and investment-network scenarios end to end.
- [x] 7.2 Test that all scenarios produce reproducible results.
- [x] 7.3 Run available tests, lint, and production build; fix regressions.
- [ ] 7.4 Check mobile and desktop layouts and remove clutter or inconsistent styles.
- [x] 7.5 Add run instructions and a short demo script.

## 8. Follow-ups (not yet done)

- [ ] 8.1 Verify live Gemini mode (`AGENT_MODE=adk` with Vertex AI or API key) end to end.
- [ ] 8.2 Mobile/desktop visual pass and accessibility audit (3.6 and 7.4 are only partially covered).
- [ ] 8.3 Deploy API/agents to Cloud Run; optionally move data to Firestore.
- [ ] 8.4 Add a graph-investigator agent for cluster summaries.
- [ ] 8.5 Persist payment state beyond process memory.
