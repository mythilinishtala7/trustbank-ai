# Capability: Investigation console

Internal, demo/judge-only experience at the separate route `/investigation` (lazy-loaded, own shell). The customer app never exposes agent names, scores, graph, or traces.

## Requirements

### Requirement: Transaction-ID entry
The console SHALL begin with an access-code gate, then a transaction ID search.

#### Scenario: Valid id
- WHEN the investigator submits a known transaction id (a payment's reference or a historical transaction id)
- THEN the console SHALL show the transaction summary, the stored assessments, the agent execution timeline, and the bounded `transaction_neighborhood` graph with evidence highlighted
- AND the full network SHALL NOT be loaded

#### Scenario: Unknown id
- THEN a clear not-found state SHALL appear

### Requirement: Live agent execution timeline
The console SHALL show the ordered execution of the orchestrator and agents: start/end time, status, duration, tool calls (name, parameters, result summary), findings, and fallbacks.

#### Scenario: Watch a payment in progress
- GIVEN the investigator opens a payment that is still being assessed or waiting for answers
- THEN the timeline SHALL update live via server-sent events (`/investigation/transactions/{id}/events`), with polling as a fallback
- AND traces SHALL be retained by the backend whether or not the console is open

### Requirement: Evidence and policy panel
The panel SHALL show each agent's status, score, confidence, evidence with provenance badges, questionnaire answers, aggregation (weights, thresholds, evidence cap), final action, and the customer-facing explanation as shown.

#### Scenario: Provenance distinguishable
- THEN `VERIFIED_SYNTHETIC`, `INFERRED`, and `USER_PROVIDED` evidence SHALL be visually distinct
- AND graph association SHALL be labelled as evidence to investigate, not proof

#### Scenario: Genuine shopkeeper transaction
- GIVEN a payment to `ben_sharma_store`
- THEN the console SHALL show no suspicious evidence and treat the recipient's volume as ordinary context

#### Scenario: Fraudulent network transaction
- GIVEN a payment to `ben_novatrade`
- THEN the graph SHALL highlight linked reported accounts and the panel SHALL list fan-in, pass-through, and link evidence with provenance

### Requirement: Graph view
Select, zoom, pan, fit, legend; selecting a node shows its id, type, and relevant evidence.

### Requirement: Access and labelling
Only the `investigator` role reaches the console (see `access-control`). All data SHALL be labelled simulated.
