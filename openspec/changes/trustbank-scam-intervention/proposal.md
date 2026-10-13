# Change: TrustBank scam intervention prototype

## Why

People can be manipulated into voluntarily sending money to scam beneficiaries. A normal authentication flow does not necessarily reveal that the payer has been socially engineered. This prototype demonstrates how a payment experience could assess available risk signals and interrupt a suspicious transaction before simulated authorization.

## What changes

- Build a coherent fictional banking experience for initiating and reviewing payments.
- Use synthetic customer, transaction, beneficiary, and fraud-network data.
- Add a deterministic and explainable risk engine.
- Visualize synthetic relationships between customers and beneficiaries in an investigator graph.
- Add contextual scam-check questions and evidence-grounded explanations.
- Simulate review, hold, cancellation, and authorization outcomes before a dummy PIN screen.
- Provide repeatable demo scenarios and automated tests.
- Build contextual-question and explanation agents with Google ADK on Gemini (Vertex AI), with a deterministic mock mode for offline demos.

## Out of scope

- Real bank, UPI, payment-network, or account integrations.
- Real money movement or collection of real PINs, passwords, or credentials.
- Claims of production-grade fraud detection or measured real-world fraud reduction.
- Training a production ML model.
- Treating an LLM as the authority for payment authorization.

## Users

- **Customer in the demo:** initiates a payment and receives a contextual intervention when relevant.
- **Hackathon judge / investigator:** explores the synthetic fraud graph and sees which evidence contributed to a risk decision.

## Success criteria

- A normal payment can reach simulated authorization without an unnecessary scam questionnaire.
- A suspicious payment is assessed before the simulated PIN screen.
- A high-risk scenario shows concrete evidence, asks contextual questions, and enters a simulated hold/review state.
- The graph shows pre-existing synthetic connections for a beneficiary with no prior complaints.
- Risk outcomes are deterministic and reproducible.
- The app runs with synthetic data and without an external AI API key.
- The UI is visually consistent, responsive, and uncluttered.
