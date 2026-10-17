# TrustBank AI: test scenarios for reviewers

Ten scenarios (S1 to S10) cover the main risk paths. All data is **synthetic** and all payments are **simulated**. No real money moves.

- App: https://trustbank-pausepay.web.app
- Investigator console: https://trustbank-pausepay.web.app/investigation
- Currency: INR. Enter the payee by its handle (for example `rahul.verma@trustpay`).
- Customer personas to log in as: **Asha Menon** (balance 5,00,000), **Priya Nair** (balance 12,400).
- Investigator console access code: supplied separately in the submission notes (not stored in this repo).

## How the system decides

Two detectors run in parallel: an **anomaly** score from the customer's own history, and a **network** score from the payee's position in the Neo4j graph. A deterministic policy combines them (0.4 anomaly, 0.6 network). Gemini only writes the questions and the plain-language explanation. It never decides the outcome.

| Score band | Outcome |
|---|---|
| Below 30 | Proceeds, no questions |
| 30 to 59 | Questions, then at most a REVIEW warning |
| 60 and above | Questions, then HOLD if the answers add risk |

A hold lasts 180 seconds, is enforced by the server, and **never auto-releases**. The customer must cancel, or confirm independent verification after it expires.

## Scenario table

| ID | Payer | Payee handle | Amount (INR) | What it tests | Expected result |
|---|---|---|---|---|---|
| S1 | Asha | `rahul.verma@trustpay` | 2,500 | Routine payment to a known person | Proceeds, no questions |
| S2 | Asha | `sharma.store@trustpay` | 1,200 | Busy, established merchant (many senders) | Proceeds. High fan-in alone is not suspicious |
| S3 | Priya | `sharma.store@trustpay` | 400 | Small customer, normal merchant | Proceeds |
| S4 | Priya | `ananya.rao@trustpay` | 600 | New-looking payee, small amount | Proceeds |
| S5 | Asha | `greenleaf.bakery@trustpay` | 450 | Young account that is legitimate | Proceeds. Account age is context, not a flag |
| S6 | Asha | `heritage.jewellers@trustpay` | 40,000 | Large but plausible purchase | REVIEW with either answer set. Never a hold |
| S7 | Asha | `spice.garden@trustpay` | 1,800 | Restaurant that forwards funds on a schedule | Proceeds. Fixed routine, not layering |
| S8 | Asha | `nova.trade@trustpay` | 25,000 | **Scam path**: fan-in plus rapid onward forwarding | Benign answers: REVIEW. Scam answers: **HOLD** |
| S9 | Priya | `nova.trade@trustpay` | 8,000 | Same payee, weaker customer anomaly | Benign answers: REVIEW. Scam answers: HOLD |
| S10 | Asha | `quick.returns@trustpay` | 5,000 | Mule account in the forwarding chain | Benign answers: REVIEW. Scam answers: HOLD |

S1 to S7 are the false-positive checks. The system should stay out of the way.

## Questionnaire answers to use

Questions use fixed options. Pick these:

| Profile | Where did you get the details | Promised a benefit | Third question |
|---|---|---|---|
| **Scam answers** | Messaging app | Yes | Pressed to hurry or keep secret (network cases), or "never met" (relationship) |
| **Benign answers** | Bank or invoice | No | No pressure (network cases), or "business vendor" (relationship) |

## Walkthrough: the main scam scenario (S8)

1. Open the app and log in as **Asha Menon**.
2. Pay `nova.trade@trustpay` 25,000 and continue to the PIN step (demo PIN shown on screen).
3. Answer the questions with the **scam answers**.
4. Expect a **HOLD** with plain-language reasons. Try the timer: only **Cancel payment** is available while it runs.
5. Repeat with the **benign answers** and expect a REVIEW warning instead, which shows that the answers change the result.
6. Open `/investigation`, enter the access code and search the payment reference (`txn_...`).

Reference numbers from a live run of S8 with scam answers: anomaly 69, network 50, answers add 40, final 98, risk HIGH, action HOLD.

## What to check in the console

1. **Timeline**: every agent step and tool call, in order, with any fallbacks shown.
2. **Graph**: Nova Trade receives from many senders, then forwards within minutes to Quick Returns, Task Rewards and Swift Assist.
3. **Evidence**: each item is labelled *inferred*, *verified synthetic* or *user provided*.
4. **Policy panel**: each score, the weights and the final action.

A graph link is evidence to investigate, not proof of guilt.

## Safety and access checks

| Check | Expected |
|---|---|
| Customer token on `/investigation/*` | 403 |
| No or bad token | 401 |
| Another customer's payment id | 404 |
| Wrong investigator code, repeated | 401, then 429 after 5 attempts |
| Customer responses | No internal scores, weights or evidence ids |
| Model misbehaviour (bad JSON, timeout, invented fields) | Safe deterministic fallback, shown in the trace |

## Run it yourself

Backend tests, from `services/backend`:

```
unset SSL_CERT_FILE
.venv/bin/python -m pytest
```

Covers all ten scenarios (`tests/test_agent_scenarios.py`), the delayed-forwarding proof, access control and model-failure fallbacks. The graph tests need a local Neo4j. Tests that need the Firestore emulator are skipped when it is not running.

Frontend tests, from `apps/banking-web`: `npx ng test --watch=false`.

## Known limits

- Data is synthetic and payments are simulated.
- The cloud deployment uses one Neo4j VM with no backups, which is acceptable for a prototype.
- A Gemini call takes about 10 to 30 seconds. If it fails, the system uses template text and the trace records the fallback.
