# Capability: Synthetic fraud network

## Requirements

### Requirement: Visualize synthetic transfer relationships
The dashboard SHALL visualize synthetic customers, beneficiary accounts, and directed transfer edges.

#### Scenario: Explore the network
- GIVEN the investigator opens the fraud dashboard
- WHEN the graph is rendered
- THEN nodes SHALL distinguish customer and beneficiary types
- AND edges SHALL represent transfer direction
- AND a visible legend SHALL explain node and risk colors

### Requirement: Inspect an entity
The dashboard SHALL let the investigator select a graph node and inspect its available synthetic evidence.

#### Scenario: Select a beneficiary
- GIVEN a beneficiary node is visible
- WHEN the investigator selects it
- THEN the detail panel SHALL show its identifier, risk signals, relevant connections, and synthetic transaction history

### Requirement: Explain graph evidence
The graph data SHALL use the same stable entity identifiers as the risk engine.

#### Scenario: Trace a flagged payment
- GIVEN a payment assessment references graph entities
- WHEN the investigator inspects those entities
- THEN the graph SHALL show the corresponding synthetic connections
- AND the dashboard SHALL NOT represent association alone as proof of fraud

### Requirement: Label synthetic intelligence
The dashboard SHALL visibly identify its dataset and intelligence as simulated.
