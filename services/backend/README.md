# TrustBank backend: status and setup

Design lives in `openspec/changes/trustbank-agentic-fraud-prevention/` (start with `tasks.md`, `knowledge-graph-data.md`).

## Status

Done: 0.2 scaffold, 0.4 OpenAPI export, 1.1-1.5 domain, fixtures, Firestore, Neo4j ingestion, `GraphService`; 2.x config, errors, auth; 3.1-3.7 agents and orchestrator; 3.8 deterministic policy; 4.x payment state machine, persistence and trace events; 6.1/6.2 customer and investigation endpoints.
Next: rest of 0.3 (Neo4j `docker-compose.yml`), the Angular apps, end-to-end tests.
Working style: one task at a time, stop for review. Risk is computed by agents only; data holds facts only.

## Run the API

Needs Firestore (emulator or real) seeded, Neo4j ingested, and two secrets (values in `.env.example`; a deployed environment rejects placeholders):

```bash
export TRUSTBANK_FIRESTORE_EMULATOR_HOST=127.0.0.1:8085 TRUSTBANK_GOOGLE_CLOUD_PROJECT=trustbank-local
export TRUSTBANK_NEO4J_PASSWORD=...            # see .env.example
export TRUSTBANK_TOKEN_SECRET=... TRUSTBANK_INVESTIGATOR_CODE=...
.venv/bin/uvicorn trustbank.main:app --port 8000
```

Routes live under `/api/v1` (`/health` is also at the root); the Angular dev proxy maps `/api` to port 8000. Without model credentials the questionnaire and explainer fall back to deterministic text (explanation `status: DEGRADED`); policy is unaffected.
Tests need the Firestore emulator (throwaway project id; skipped if it is down). Regenerate the schema after API changes: `.venv/bin/python -m trustbank.openapi_export > openapi.json` (a test fails if it is stale).

## Local setup

```bash
cd services/backend
uv venv --python /opt/homebrew/bin/python3.14 .venv   # 3.12 download blocked by corporate TLS
unset SSL_CERT_FILE; UV_NATIVE_TLS=1 uv pip install -e ".[dev]"
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy src tests
cp ../../infra/.env.example .env   # then fill TRUSTBANK_TOKEN_SECRET and TRUSTBANK_INVESTIGATOR_CODE
```

`SSL_CERT_FILE` in the shell breaks `uv`; hence the unset. Check Google ADK works on Python 3.14 before the agents slice.

## Firestore

Real project: `project-b63ed173-f777-4777-81a`, database `(default)` in `asia-southeast1` (Singapore). Seeded with the synthetic dataset.

- Console: https://console.firebase.google.com/project/project-b63ed173-f777-4777-81a/firestore
- Owner account: `teamdynaminds3@gmail.com`. gcloud needs `export CLOUDSDK_PYTHON=/opt/homebrew/bin/python3.14`.
- Application default credentials must be that account (browser may pick the wrong one; use incognito):
  `gcloud auth application-default login`, then check the token email.

Emulator:

```bash
firebase emulators:start --only firestore --config infra/firebase.emulator.json --project trustbank-local
export TRUSTBANK_FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
.venv/bin/python -m trustbank.seed --reset
```

Real Firestore (unset the emulator variable):

```bash
.venv/bin/python -m trustbank.seed --remote project-b63ed173-f777-4777-81a [--reset] [--yes]
```

Timestamps are relative to seed time; reseed before a demo.

## Knowledge graph (Neo4j)

Neo4j 5 at `bolt://localhost:7687` (`TRUSTBANK_NEO4J_URI`, `TRUSTBANK_NEO4J_USER`, `TRUSTBANK_NEO4J_PASSWORD`).
Firestore stays the system of record; the graph is projected from it. Ingest is idempotent (MERGE on stable ids):

```bash
export TRUSTBANK_FIRESTORE_EMULATOR_HOST=127.0.0.1:8085
.venv/bin/python -m trustbank.seed --reset            # Firestore
.venv/bin/python -m trustbank.graph.ingest [--reset]  # Neo4j; --reset clears the five labels first
```

Seeding does not ingest. Reseed Firestore, then re-run ingest (timestamps are relative to seed time).
Integrity violations are printed and the command exits non-zero.

## Agents and Gemini

`build_orchestrator(settings, graph, repo)` returns the ADK orchestrator. The anomaly and fraud-network agents are
deterministic custom ADK agents; the questionnaire and explainer are `LlmAgent`s on Gemini through Vertex AI
(`TRUSTBANK_MODEL_NAME`, default `gemini-2.5-flash`; needs `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION` and ADC
with `aiplatform.endpoints.predict`). `GOOGLE_GENAI_USE_VERTEXAI` defaults to `TRUE`. Behind a corporate TLS proxy,
point `SSL_CERT_FILE` at a bundle that includes the proxy CA plus the public roots. Without Gemini access the
questionnaire and explainer degrade to fixed questions and a template explanation.

Tests: graph and scenario tests need the running Neo4j (they rebuild it from the deterministic dataset, so re-run ingest
afterwards if you want the seeded data back). Live Gemini smoke test: `.venv/bin/pytest -m live`.
## Seed, then load the knowledge graph

Order: Firestore (source of truth) first, then Neo4j (derived, rebuildable). Both are idempotent.

```bash
docker compose -f ../../infra/docker-compose.yml up -d          # local Neo4j
.venv/bin/python -m trustbank.seed --remote project-b63ed173-f777-4777-81a --reset --yes
.venv/bin/python -m trustbank.ingest --reset --remote-firestore project-b63ed173-f777-4777-81a
# expected: ingested: 22 customers, 15 beneficiaries, 37 accounts, 279 transactions, 2 connections; integrity OK
```

Against the VM Neo4j, open the IAP tunnel (see `infra/README.md`) and load `.env.vm` values
(`TRUSTBANK_NEO4J_URI=bolt://localhost:7688`, user, password) before running `ingest`.
Fixture timestamps are relative to seed time, so reseed and re-ingest before a demo.

## Sample graph queries

Cypher (Neo4j Browser at http://localhost:7474, user `neo4j`):

```cypher
// whole picture
MATCH (n) RETURN n LIMIT 200
// who paid Nova Trade, and how much
MATCH (s:Account)-[:SENT]->(t:Transaction)-[:PAID]->(:Beneficiary {id:'ben_novatrade'})
RETURN s.id, t.amount, t.timestamp ORDER BY t.timestamp
// connections between accounts (evidence to investigate, not proof)
MATCH (a:Account)-[c:CONNECTED_TO]-(b:Account) RETURN a, c, b
```

Python (`GraphService`; every query takes an explicit `as_of`):

```python
from datetime import timedelta
from trustbank.config import get_settings
from trustbank.graph import create_driver
from trustbank.graph_service import GraphService
from trustbank.store import DatasetRepository, create_client

settings = get_settings()
repo = DatasetRepository(create_client(settings))
graph = GraphService(create_driver(settings))
as_of = repo.get_beneficiary("ben_novatrade").first_seen_at + timedelta(days=3)

graph.account_age_days("acct_novatrade", as_of)  # 3
graph.flow_profile("acct_novatrade", 72, as_of)  # retention 0.02, median dwell 6 min, 8 senders
graph.recent_senders("acct_novatrade", 72, as_of)
graph.forwarding_chain(
    "acct_novatrade", "forward", 72, as_of
)  # Quick Returns -> Task Rewards -> Swift Assist
graph.transaction_neighborhood("txn_hist_8", depth=2)
```

## Run the API

```bash
.venv/bin/uvicorn --factory trustbank.main:create_app --port 8000
curl localhost:8000/api/v1/health
```

## Not done yet

- Deny-all `firestore.rules` are not deployed to the real project
  (`firebase deploy --only firestore --config infra/firebase.emulator.json`). The `transactions` composite index
  was created with gcloud and is READY.
- Confirm policy defaults (weights 0.4/0.6, thresholds 30/60, 180 s hold).
- Cloud Run to the VM Neo4j connectivity is task 7.2. The VM graph is not yet re-ingested with `account_number`.
- Old TypeScript prototype (`apps/banking-web`, `services/fraud-api`, `services/agents`) stays until task 7.3.
