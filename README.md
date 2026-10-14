# TrustBank — OpenSpec Starter

This folder is a starter specification for a hackathon prototype: a fictional banking app that demonstrates AI-assisted scam prevention before simulated payment authorization.

## How to use it

1. Copy `openspec/` and `COPILOT_INSTRUCTIONS.md` into your repository.
2. Review the proposal and design against your existing codebase. Treat the current repository's framework and conventions as authoritative.
3. Install/use the OpenSpec CLI your team already prefers, then validate the change using your installed version's commands.
4. Ask Copilot to implement one task at a time from `openspec/changes/trustbank-agentic-fraud-prevention/tasks.md`.
5. Keep this change folder until implementation and acceptance checks are complete; archive it using your team's OpenSpec workflow.

> OpenSpec CLI commands and file conventions can vary by version. Follow the version installed in your repository if it differs from this starter structure.

## Suggested parallel work split

- **Developer A — Banking UX:** payment flow, transaction history, simulated authorization, visual design system.
- **Developer B — Fraud intelligence:** synthetic dataset, deterministic risk engine, graph visualization and node details.
- **Shared integration — AI intervention:** connect the risk results to contextual questions, explanations, and the simulated hold. Agree on the API/data contracts before parallel implementation.

Do not have both developers modify the same files at the same time. Integrate via small PRs and shared TypeScript interfaces.

## Product guardrails

- All customers, accounts, transfers, risk indicators, and outcomes are synthetic.
- No real banking integration, real money movement, or real PIN collection.
- The LLM explains verified signals and interprets context; deterministic code owns the risk decision and simulated payment state.
- A new/unfamiliar beneficiary alone must not be labeled fraudulent.
- Do not claim the prototype has proven real-world fraud reduction.

## Run the prototype

Requires Node 20+. Ports: API `3100`, web `4300`.

```bash
# Terminal 1 — API + agents (mock mode, no keys needed)
cd services/agents && npm install
cd ../fraud-api && npm install && npm run dev

# Terminal 2 — web app
cd apps/banking-web && npm install && npx ng serve --port 4300
```

Open http://localhost:4300 (customer app) and http://localhost:4300/investigator. Walkthrough: `docs/demo-script.md`.

### Tests

```bash
cd services/agents && npm test
cd services/fraud-api && npm test
cd apps/banking-web && npx ng test --watch=false
```

### Gemini agents (Google ADK)

Default is deterministic mock agents. To use Gemini through Google ADK, set before `npm run dev` in `services/fraud-api`:

```bash
export AGENT_MODE=adk
# Vertex AI:
export GOOGLE_GENAI_USE_VERTEXAI=TRUE GOOGLE_CLOUD_PROJECT=<project> GOOGLE_CLOUD_LOCATION=us-central1
# or API key:  export GOOGLE_API_KEY=<key>
export GEMINI_MODEL=gemini-2.5-flash   # optional
```

Keys stay server-side. If the model errors or returns ungrounded output, the app falls back to deterministic explanations and logs it in the decision trace. Agent design: `openspec/changes/trustbank-agentic-fraud-prevention/design.md`.
