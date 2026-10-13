# Design: TrustBank scam intervention prototype

## Product principles

1. **Quiet protection:** normal payments remain simple; intervention appears only when the risk policy warrants it.
2. **Evidence before alarm:** explain concrete signals and avoid declaring fraud without sufficient evidence.
3. **Deterministic control:** code, not an LLM, decides the simulated payment state.
4. **Synthetic by design:** all data and outcomes are fictional and clearly identified as simulated where appropriate.
5. **One product, two views:** a customer-facing banking flow and a separate investigator-facing fraud graph.

## Visual direction

- Premium, calm, light-theme fintech.
- Navy `#14243A`, royal blue `#2864E8`, off-white `#F7F8FA`, muted gray `#697586`, amber `#D99116`, danger red `#D92D20`.
- Clean sans-serif typography, consistent 8px spacing rhythm, restrained borders, limited shadows, generous whitespace.
- Blue/neutral for normal states, amber for caution, red only for high-risk interventions.
- Avoid excessive gradients, glassmorphism, neon/glowing nodes, giant AI illustrations, nested cards, and decorative metrics.
- Each screen has one clear primary action.

## Customer journey

1. Home and transaction history.
2. Choose payment method.
3. Enter recipient details.
4. Enter amount and optional payment note.
5. Run silent synthetic risk evaluation.
6. If policy requires review, show a risk summary and ask up to two contextual questions.
7. Recalculate the deterministic policy outcome using verified signals and normalized answer categories.
8. For high risk, show evidence, a simulated temporary hold, independent verification guidance, and cancellation.
9. For low risk, show a concise transaction review and proceed to a clearly simulated PIN/authorization screen.
10. Show receipt or cancellation result and update synthetic transaction history.

## Investigator journey

- Open a separate dashboard with a central network graph.
- Nodes represent synthetic customers and beneficiary accounts.
- Directed edges represent transfers and display amount/time on selection.
- Selecting a node opens a side panel with identifier, risk signals, connected nodes, and synthetic transfer history.
- Include a legend, fit-to-view, zoom/pan, and a small summary. The graph remains the main focus.
- Label the view as simulated fraud intelligence.

## Risk policy contract

The risk engine returns:
- `score`: integer from 0 to 100.
- `level`: `LOW`, `MEDIUM`, or `HIGH`.
- `signals`: typed list of evidence items, each with an id, label, explanation, and severity.
- `recommendedAction`: `PROCEED`, `REVIEW`, `HOLD`, or `CANCEL`.
- `beneficiaryId` and relevant graph entity identifiers.
- `explanation`: deterministic evidence summary suitable for fallback display.

Initial thresholds should be configurable, not scattered through components. Suggested demo defaults: 0–29 LOW, 30–59 MEDIUM, 60–100 HIGH. Thresholds are illustrative and must be tuned to the synthetic scenarios. A new beneficiary or amount deviation alone must not automatically produce HIGH.

The LLM may select/phrase questions and explain supplied evidence. It cannot create evidence or override the deterministic action. If the LLM fails, use the deterministic explanation.

## Data contracts

Create typed, framework-appropriate equivalents of:

- `CustomerProfile`: id, displayName, baseline transaction summary.
- `Beneficiary`: id, displayName, masked account reference, bank label, firstSeenAt, synthetic risk metadata.
- `Transaction`: id, customerId, beneficiaryId, amount, currency, note, timestamp, status, scenarioId.
- `RiskSignal`: id, category, severity, title, evidence, sourceEntityIds.
- `RiskAssessment`: score, level, signals, recommendedAction, explanation.
- `GraphNode`: id, type, label, riskLevel, metadata.
- `GraphEdge`: id, source, target, amount, timestamp, status.
- `ScamCheckAnswers`: sourceOfDetails, promisedBenefit.
- `PaymentDemoState`: payment details, assessment, answers, intervention state, final simulated outcome.

Keep UI models separate from any graph-library-specific types.

## Synthetic demo scenarios

1. **A · Normal rent payment:** ₹2,500 to a familiar landlord, consistent with the customer baseline, no graph links. Outcome: LOW / PROCEED, no questions.
2. **B · New recipient, linked network:** ₹25,000 to a 3-day-old handle with no complaints but direct links to flagged synthetic accounts and a burst of incoming transfers. Initial outcome: MEDIUM / REVIEW; scam-check questions follow. Benign answers (friend/family, no promise) stay REVIEW.
3. **C · High-confidence scam interception:** same payment as B; user answers "Telegram/WhatsApp" and "promised payouts". Outcome: HIGH / HOLD with a 120-second simulated cooling-off timer; PIN step locked.

B and C share one beneficiary on purpose: the graph evidence is identical and only the user's answers change the outcome.

Scenario data must be consistent across payment view, graph, explanation, and history. Do not imply that graph association proves guilt.

## Architecture (implemented)

- `apps/banking-web`: Angular (standalone components, signals) + Cytoscape.js (lazy-loaded investigator route). Plain CSS design tokens; Tailwind from the original pitch is deferred.
- `services/fraud-api`: Node/Express (TypeScript). Owns synthetic store, graph queries, deterministic risk engine, and payment state machine (`SCAM_CHECK`, `REVIEW`, `HOLD`, `READY_FOR_AUTH`, `COMPLETED`, `CANCELLED`). Authorization is rejected server-side unless the state is `READY_FOR_AUTH`.
- `services/agents`: Google ADK (TypeScript) agents on Gemini, plus deterministic mock agents. Selected by `AGENT_MODE=adk` (default: mock).
- `CANCEL` is a user-initiated terminal state; the policy itself returns `PROCEED`, `REVIEW`, or `HOLD`.
- Default local ports: API 3100, web 4300 (4200/3000 are often taken).

## Agent design

| Agent | Role | May do | Must not |
|---|---|---|---|
| Payment orchestrator (plain code) | Owns state machine and policy action | Decide PROCEED/REVIEW/HOLD, enforce hold | Delegate decisions to an LLM |
| `scam_check_agent` (ADK LlmAgent) | Phrase the two scam-check questions | Reword questions | Add questions, change answer options |
| `explainer_agent` (ADK LlmAgent) | Plain-language explanation of verified signals | Summarize and cite signal ids | Cite unknown signal ids, invent facts, change action |

Agent inputs contain only deterministic signals (never user free text). Outputs are validated with zod schemas and signal-id grounding checks; any error or invalid output falls back to deterministic text and is recorded in the decision trace. Later candidates: a graph-investigator agent summarizing clusters for the dashboard, and Vertex AI deployment on Cloud Run.

## Failure and privacy handling

- No real account credentials or PIN values are stored or sent.
- Simulated PIN entry accepts a dummy value only, never logs the value, and is clearly labeled as a demo.
- External model access is optional and must be server-side if used. Do not expose secrets in the client.
- If model calls fail, continue using deterministic rules and explanations.
- Treat free-text messages as untrusted input.
- Provide cancellation and back navigation at all nonterminal steps.
