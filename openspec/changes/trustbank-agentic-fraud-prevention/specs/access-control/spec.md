# Capability: Access control

The product is a payment-flow demo, not a bank. Customers enter with a dummy login; the internal investigation console is protected by a demo-only access code, enforced on the backend.

## Requirements

### Requirement: Dummy customer entry
The customer app SHALL let the user enter as a seeded synthetic persona without credentials.

#### Scenario: Enter as a persona
- WHEN the user picks a persona (for example "Asha Menon" or "Priya Nair") on the entry screen
- THEN the backend SHALL issue a short-lived session token (default 8 hours) bound to that customer id and role `customer`
- AND no password, real identity, or real credential SHALL be collected
- AND the entry screen SHALL state that this is a simulated demo

#### Scenario: Customer isolation
- GIVEN a customer token
- WHEN it requests another customer's payment
- THEN the server SHALL respond 404

### Requirement: Investigator access code
The investigation console SHALL require a demo access code.

#### Scenario: Unlock the console
- WHEN a valid code is posted to `/auth/investigator`
- THEN the server SHALL issue a short-lived token with role `investigator`
- AND the code SHALL come from server configuration, never be committed, hard-coded in the client, or logged
- AND invalid attempts SHALL return a generic 401 and be rate-limited per IP

### Requirement: Backend enforcement
Every `/investigation/*` endpoint SHALL require the `investigator` role on the server. Hiding a route or button SHALL NOT be treated as access control.

#### Scenario: Customer calls investigation API
- THEN the server SHALL respond 403, and customer responses SHALL never contain investigation fields

#### Scenario: Missing or expired token
- THEN the server SHALL respond 401 and the UI SHALL return to its entry screen

### Requirement: Token integrity
Tokens SHALL be signed with a server secret from configuration and carry role, subject, and expiry.

### Requirement: Audit
Each investigation lookup SHALL write an `audit_log` entry (time, transaction id).
