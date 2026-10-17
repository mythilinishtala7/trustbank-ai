# Demo script and speaker notes (4 minutes)

Live app: https://trustbank-pausepay.web.app. Console access code: Secret Manager `trustbank-investigator-code`. All data is synthetic; no real money or PIN.

## Before you start (2 minutes of prep)

- Start the Neo4j VM if it is stopped: `gcloud compute instances start trustbank-neo4j --zone asia-southeast1-b`. Check `/api/v1/health` shows `neo4j: ok`.
- Tab 1: architecture diagram. Tab 2: customer app, signed out. Tab 3: `/investigation`, already unlocked.
- Do one dry run of the Nova Trade payment shortly before. Questions and the explanation take 10 to 30 seconds (two Gemini calls), so know what you will say while it loads.
- Backup: keep one finished `txn_` reference from the dry run so you can open the console even if the live payment stalls.

## Timeline

| Time | What | Where |
|---|---|---|
| 0:00 to 0:50 | Problem and architecture | Diagram |
| 0:50 to 1:25 | Routine payment, no friction | Customer app |
| 1:25 to 2:45 | Scam scenario: questions, hold | Customer app |
| 2:45 to 3:35 | How the agents decided | Console |
| 3:35 to 4:00 | Fairness and close | Console or diagram |

## 1. Problem and architecture (0:00 to 0:50)

Say:
- "Scam payments are authorised by the victim, so passwords and PINs do not stop them. The moment to act is **before authorization**."
- "TrustBank AI checks each payment as it is created. It uses four agents, a knowledge graph and a strict, deterministic policy."

Point at the diagram, left to right:
1. **Angular app**: one customer experience, plus a protected `/investigation` console.
2. **FastAPI backend and orchestrator** (Google ADK): runs the agents.
3. **Anomaly agent**: how unusual is this payment for *this* customer. Deterministic, uses Firestore history.
4. **Fraud-network agent**: how does the recipient *behave*. Deterministic, uses Neo4j graph queries.
5. **Questionnaire and explainer agents** (Gemini): ask the customer fixed-choice questions and explain the outcome in plain language.
6. **Risk policy**: deterministic. Agents give evidence, only the policy decides: proceed, review, hold.

Key sentences:
- "The model never decides. It asks questions and writes explanations; scores and actions come from code."
- "The data holds facts only. There are no stored flags, complaints or scores. Every risk signal is computed from behavior."

## 2. Routine payment (0:50 to 1:25)

Do: enter as **Asha Menon**, pay `rahul.verma@trustpay` 2,500, go to the demo PIN, confirm.

Say: "Normal payment, known recipient, no questions, no delay. Good protection must not annoy genuine customers."

## 3. Scam scenario (1:25 to 2:45)

Do: Asha pays `nova.trade@trustpay` 25,000. While it loads, talk.

Say while loading:
- "Two detectors run in parallel. One checks Asha's history, the other queries the graph around the recipient."

When questions appear:
- "Three questions, fixed answer options, so the customer cannot talk the system into anything. Free text is treated as untrusted."
- Answer: messaging app, promised a return, pressed to hurry.

When the hold appears:
- "Payment paused, plain-language reasons, no jargon and no accusation. The 3-minute timer is enforced by the **server**, not the browser, and it never auto-releases: the customer must cancel or confirm they verified independently."
- Click **Cancel payment**. Do not wait out the timer.

Optional contrast (10 seconds): "With benign answers, such as an invoice and no promised return, the same payment ends in a review warning, not a hold. The customer's answers matter."

## 4. Console (2:45 to 3:35)

Do: switch to `/investigation`, search the `txn_` reference.

Walk top to bottom:
1. **Timeline**: "Every tool call and finding, in order. Nothing is hidden."
2. **Graph**: "Nova Trade forwards money to Quick Returns, then Task Rewards, then Swift Assist, each within minutes. Eight senders fan in. That is a layering pattern."
3. **Evidence**: "Each item has provenance. *Inferred* means computed from transactions. *Verified synthetic* means a declared fact. *User provided* is the customer's answer."
4. **Policy panel**: "Anomaly 69, network 50, answers added 40 points. Final 98, HIGH, action HOLD."

Say: "A graph connection is evidence to investigate, not proof of guilt."

## 5. Fairness and close (3:35 to 4:00)

Say:
- "Spice Garden also passes most of its money onward, but it holds funds for hours, uses one hop and a regular daily schedule. It is **not** flagged. Heritage Jewellers is an unusual amount, so the customer gets questions and a review warning, but never a hold, because the graph shows nothing wrong."
- "A new recipient or limited history is never high risk on its own. We need at least two independent behaviors."
- Close: "Real ADK agents, real graph queries, real Gemini calls, deployed on Cloud Run and Firebase Hosting. The money movement is simulated; the risk detection is not."

## Questions you may get

- **Why not let Gemini decide?** Auditability and safety: model output cannot change the policy, and invalid output falls back to fixed questions and template text. We tested injection and bad JSON.
- **What if Gemini is down?** The payment still completes with fixed questions and a template explanation; the policy result is unchanged.
- **Is it flagging real people?** No, all data is synthetic and outcomes are computed, never stored.
- **Where is the graph hosted?** Self-hosted Neo4j on a private Compute Engine VM, reached from Cloud Run over a VPC connector.
- **What is out of scope?** Appeals, investigator resolution and real accounts.

## If something goes wrong

- Payment stalls over 40 seconds: say "the models are thinking", then open the backup `txn_` in the console and continue from step 4.
- Console shows no graph: check the VM is running; use the backup transaction.
