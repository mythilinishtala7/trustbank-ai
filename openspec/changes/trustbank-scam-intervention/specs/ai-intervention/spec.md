# Capability: AI scam intervention

## Requirements

### Requirement: Contextual scam-check questions
The intervention SHALL ask up to two concise questions when the risk policy recommends review or stronger intervention.

#### Scenario: Suspicious job-fee context
- GIVEN the assessment indicates suspicious job-related context
- WHEN the intervention begins
- THEN it SHALL ask how the recipient details were obtained and/or whether a job-related benefit or fee was promised
- AND SHALL present accessible, concise answer choices

### Requirement: Evidence-grounded explanation
The intervention SHALL explain the strongest verified signals in plain language.

#### Scenario: Explain high risk
- GIVEN a HIGH assessment with specific risk signals
- WHEN the warning is displayed
- THEN the warning SHALL identify those signals
- AND SHALL NOT invent recipient history, complaints, or graph connections

### Requirement: Deterministic policy control
The LLM SHALL NOT independently authorize, block, hold, or release a simulated payment.

#### Scenario: Model recommends a different action
- GIVEN the deterministic policy returns `HOLD`
- WHEN the model response suggests proceeding
- THEN the application SHALL preserve the policy's `HOLD` action

### Requirement: Fallback behavior
The application SHALL remain usable without an external AI service.

#### Scenario: AI provider unavailable
- GIVEN the model provider is missing or returns an error
- WHEN an intervention is required
- THEN the application SHALL show a deterministic explanation based on verified synthetic evidence
- AND SHALL preserve the deterministic risk action

### Requirement: Simulated temporary hold
The application MAY apply a short simulated hold for a high-risk demo scenario.

#### Scenario: High-risk payment
- GIVEN the deterministic policy recommends `HOLD`
- WHEN the user reaches the intervention
- THEN the application SHALL show why the payment is paused, provide cancellation and independent verification guidance, and keep the authorization step inaccessible while the simulated hold is active
- AND SHALL NOT imply that a real bank or payment network has enforced the hold

### Requirement: Google ADK agents with guarded output
The application SHALL implement question phrasing and explanation as Google ADK agents backed by Gemini, selectable by configuration, with a deterministic mock provider as default.

#### Scenario: Model cites unknown evidence
- GIVEN the explainer agent returns a signal id that was not supplied
- WHEN the output is validated
- THEN the application SHALL discard it and use the deterministic explanation
- AND SHALL record the fallback in the decision trace

### Requirement: Cooling-off duration
The simulated hold for a HIGH assessment SHALL default to 120 seconds and be configurable.

#### Scenario: Hold elapsed
- GIVEN a payment is on simulated hold
- WHEN the timer has not elapsed
- THEN the server SHALL reject continuation and authorization
- AND WHEN it has elapsed THEN the user MAY choose to continue to the PIN step or cancel
