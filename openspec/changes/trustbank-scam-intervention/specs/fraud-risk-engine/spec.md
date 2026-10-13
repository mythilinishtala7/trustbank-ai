# Capability: Fraud risk engine

## Requirements

### Requirement: Explainable assessment
The risk engine SHALL return a deterministic assessment containing a score, level, contributing signals, evidence, and recommended action.

#### Scenario: Assess a normal payment
- GIVEN a familiar beneficiary and a transaction consistent with the synthetic customer profile
- WHEN the engine assesses the payment
- THEN it SHALL return the configured LOW outcome for the normal demo fixture
- AND SHALL provide an explanation consistent with the evidence

### Requirement: Use multiple signals
The risk engine SHALL consider transaction deviation, beneficiary familiarity, available synthetic recipient/network signals, and scam context as distinct inputs.

#### Scenario: New beneficiary without complaints
- GIVEN a beneficiary has no prior complaint record
- AND the synthetic graph contains multiple relevant suspicious connections
- WHEN the engine assesses a payment to that beneficiary
- THEN it MAY assign elevated risk based on those connections and other evidence
- AND SHALL NOT claim that the beneficiary has prior complaints

### Requirement: Avoid unsupported conclusions
The risk engine SHALL NOT label a payment HIGH solely because the beneficiary is new or the amount is unusual.

#### Scenario: Unusual legitimate payment
- GIVEN a payment is unusual but there are no other meaningful suspicious signals
- WHEN the engine assesses the payment
- THEN the outcome SHALL follow the configured policy without asserting that the payment is fraudulent

### Requirement: Reproducible demo
The engine SHALL produce repeatable results for fixed scenario inputs and configured thresholds.

### Requirement: Evidence cap
Without network or complaint evidence, the score SHALL be capped below the HIGH threshold unless user-provided context alone is strong (both context signals present).

#### Scenario: New handle and large amount only
- GIVEN an unknown recipient and an amount far above baseline
- WHEN no network, complaint, or strong context evidence exists
- THEN the level SHALL NOT be HIGH
