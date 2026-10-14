# Copilot instructions for TrustBank
test 
You are implementing a polished, demo-ready prototype from the OpenSpec change. Follow the specifications before writing code.

## First actions

1. Inspect the existing repository, package scripts, framework versions, routing, component conventions, tests, and current design system.
2. Do not replace the existing framework or restructure the whole repository without approval.
3. Read:
   - `openspec/changes/trustbank-scam-intervention/proposal.md`
   - `openspec/changes/trustbank-scam-intervention/design.md`
   - `openspec/changes/trustbank-scam-intervention/tasks.md`
   - all specs under `openspec/changes/trustbank-scam-intervention/specs/`
4. Report the repository's current architecture and identify the first small task to implement.
5. Implement only the requested task. Do not generate the entire application in one response.

## Product intent

TrustBank is a fictional banking experience whose differentiator is intervention before simulated payment authorization. It should feel like a premium, calm, credible banking product—not a generic admin dashboard, chatbot, or cybersecurity game.

## Design constraints

- Use a restrained light theme, generous whitespace, strong hierarchy, and consistent spacing.
- Suggested tokens: navy `#14243A`, blue `#2864E8`, off-white `#F7F8FA`, muted text `#697586`, amber `#D99116`, danger `#D92D20`.
- Use red only for high-risk interventions, amber for caution, and neutral/blue for normal states.
- Avoid excessive gradients, glowing AI graphics, nested cards, decorative charts, and needless animation.
- Keep each screen focused on one primary action.
- The payment flow must look like one coherent banking app from start to finish.
- The fraud network is a separate investigator view. Make the graph readable and interactive, with a legend, selectable nodes/edges, and a detail panel.
- Never use real bank logos, real credentials, or real customer data.

## Engineering constraints

- Follow the repository's existing framework and conventions. If it is Angular, prefer its existing version, standalone-component patterns, services, and test setup.
- Keep UI, synthetic data, risk policy, graph queries, and AI explanation concerns separate.
- Use typed models and explicit interfaces. Avoid `any` unless there is a documented reason.
- Make demo scenarios deterministic and reproducible.
- Add or update tests for each meaningful behavior.
- Do not add dependencies without explaining why and checking compatibility with the existing stack.
- Do not expose API keys in frontend code. The app must work in mock-agent mode without an external model.
- Do not pretend that a frontend countdown is a bank-enforced hold; this is a simulated state inside the prototype.

## Risk and safety rules

- Deterministic risk policy controls `PROCEED`, `REVIEW`, `HOLD`, and `CANCEL` outcomes.
- An LLM must not independently authorize, block, or release a payment.
- Only use facts in the supplied synthetic evidence. Never invent reports, account links, or transaction history.
- A new beneficiary or an unusual amount is a signal, not proof of fraud.
- Treat user-provided messages and text as untrusted input.
- Fail safely if the AI service is unavailable: show a deterministic, evidence-based explanation.

## Implementation workflow

For every task:
1. State which task and files you intend to change.
2. Implement the smallest complete increment.
3. Run relevant tests, lint, and build commands available in the repo.
4. Report changed files, tests run, outcomes, and known gaps.
5. Do not mark a task complete if its acceptance criteria are not met.
6. Do not silently expand scope. Suggest a separate OpenSpec change for unrelated work.
