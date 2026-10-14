# Capability: Customer experience

A simple payment-flow app. The focus is the payment and intervention, not banking features.

## Requirements

### Requirement: Dummy entry and home
The app SHALL open on a persona picker (no credentials), then a minimal home with balance, a Pay action, and the last few transactions.

### Requirement: Minimal customer view
The customer API and UI SHALL expose only what is needed to explain a warning.

#### Scenario: What the customer sees
- THEN responses SHALL contain: payment status, recipient display name, amount, a plain-language explanation, a short list of customer-readable reasons, questions and options, hold end time, available actions, and a payment reference
- AND SHALL NOT contain agent names, numeric risk scores, thresholds, graph data, tool calls, other customers' identifiers or names, or internal evidence ids

### Requirement: Payment journey
Choose recipient (UPI id or 9–18 digit account number) → amount and note → review → outcome.

#### Scenario: Low risk
- GIVEN the backend returns `READY_FOR_AUTH`
- THEN the app SHALL go straight to the simulated PIN screen without questions

#### Scenario: Unknown recipient
- THEN it SHALL be shown as unverified, not fraudulent

### Requirement: Scam-check questions
When the state is `QUESTIONNAIRE`, show the returned questions (at most 3) with fixed options and an optional free-text field (300 chars); submit answers.

### Requirement: Review
For `REVIEW`, show the explanation and reasons, and require explicit acknowledgement before the PIN step.

### Requirement: Simulated hold
For `HOLD_ACTIVE`, show why the payment is paused, a countdown driven by the server's `hold_until`, independent-verification guidance, and Cancel. No path to the PIN screen SHALL exist.

#### Scenario: Hold expiry
- WHEN the countdown ends
- THEN the app SHALL refetch the payment, show `HOLD_EXPIRED`, and offer Cancel or "I verified the recipient independently" then Continue
- AND SHALL NOT proceed automatically

### Requirement: Simulated PIN and receipt
Demo-labelled PIN screen (4–6 digits); receipt labelled simulated, showing the payment reference.

### Requirement: States and accessibility
Loading, error (including 503), and empty states. Keyboard-accessible labelled controls; mobile and desktop layouts.

### Requirement: Visual consistency
Design tokens in `design.md`; red only for high-risk interventions; one primary action per screen.
