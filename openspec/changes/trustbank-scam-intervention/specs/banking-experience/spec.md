# Capability: Banking experience

## Requirements

### Requirement: Simulated payment journey
The application SHALL let a user move from a fictional banking home screen through beneficiary entry and payment details to a simulated outcome.

#### Scenario: Initiate a payment
- GIVEN the user is on the banking home screen
- WHEN the user chooses Pay and supplies valid synthetic beneficiary and amount details
- THEN the application SHALL create a pending simulated payment
- AND SHALL run risk assessment before displaying simulated authorization

### Requirement: Normal payment
The application SHALL keep the normal payment path concise when the risk policy recommends `PROCEED`.

#### Scenario: Low-risk payment
- GIVEN a payment has a LOW assessment and action `PROCEED`
- WHEN the user reviews the payment
- THEN the application SHALL allow the user to continue to simulated authorization
- AND SHALL NOT require scam-check questions

### Requirement: Simulated authorization
The application SHALL clearly identify authorization and receipts as simulated.

#### Scenario: Complete a demo payment
- GIVEN the risk policy allows continuation
- WHEN the user enters the demo authorization step and confirms
- THEN the application SHALL record a synthetic completed transaction
- AND SHALL NOT send a real payment or store a real PIN

### Requirement: Cancellation
The application SHALL let the user cancel before simulated completion.

#### Scenario: Cancel a payment
- GIVEN a payment is pending, under review, or on simulated hold
- WHEN the user chooses Cancel payment
- THEN the application SHALL mark the simulated payment cancelled
- AND SHALL prevent the authorization screen from being reached for that payment

### Requirement: Recipient by UPI ID or account number
The application SHALL accept a UPI ID or a 9–18 digit account number as recipient and SHALL treat recipients absent from synthetic records as unverified rather than fraudulent.

### Requirement: Review acknowledgement
When the policy action is `REVIEW`, the application SHALL show the evidence and require explicit acknowledgement before the simulated PIN step.
