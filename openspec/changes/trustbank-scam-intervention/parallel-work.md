# Parallel development plan

## Before splitting work

Agree on these contracts first:
- Shared TypeScript types.
- Scenario IDs and fixture names.
- Risk thresholds and action mapping.
- Service interfaces.
- Routing/navigation boundaries.
- CSS token names and shared components.

## Workstream A: Banking UX

Own:
- Home, payee entry, amount, review, authorization simulation, receipt, history.
- Shared visual tokens and basic form controls.

Avoid editing:
- Fraud engine implementation.
- Graph rendering components.
- Risk policy thresholds, except through the agreed contract.

Deliver:
- Screens with mocked service calls and typed interfaces.
- Component tests for navigation, validation, cancellation, and payment state.

## Workstream B: Fraud intelligence

Own:
- Synthetic customer/beneficiary/transaction fixtures.
- Typed graph model and graph query service.
- Deterministic risk engine and unit tests.
- Investigator graph and entity detail panel.

Avoid editing:
- Banking page layouts.
- Payment navigation and simulated PIN screen.

Deliver:
- Stable risk and graph service interfaces.
- Three repeatable scenarios with evidence.
- Unit tests for LOW, REVIEW, and HIGH.

## Shared integration

One person owns integration PRs. Connect the payment flow to the risk service, then to intervention screens. Keep the AI adapter behind an interface and begin with mock mode.

## Git workflow

- Create short-lived branches per task or workstream.
- Do not let both developers edit shared types independently.
- Merge the data contracts first, then work in parallel.
- Open small PRs with tests and screenshots for UI changes.
- Rebase/merge frequently; do not accumulate a large integration branch.

## Workstream C: Agents (`services/agents`)

Own: ADK agent definitions, prompts, output schemas, guardrails, mock provider, and agent tests.
Avoid editing: risk engine scoring and payment state machine. Interface: `AgentProvider` in `services/agents/src/types.ts`.
