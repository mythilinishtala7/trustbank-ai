# TrustBank backend: status and setup

Design lives in `openspec/changes/trustbank-agentic-fraud-prevention/` (start with `tasks.md`, `knowledge-graph-data.md`).

## Status

Done: 0.2 scaffold, 1.1 domain models, 1.2 deterministic fixtures, 1.3 Firestore repository + seed.
Next: rest of 0.3 (Neo4j `docker-compose.yml`, `.env.example`), then 1.4 Neo4j ingestion, 1.5 `GraphService` queries.
Working style: one task at a time, stop for review. Risk is computed by agents only; data holds facts only.
No new tests unless asked (author preference). Existing `tests/test_fixtures.py` stays.

## Local setup

```bash
cd services/backend
uv venv --python /opt/homebrew/bin/python3.14 .venv   # 3.12 download blocked by corporate TLS
unset SSL_CERT_FILE; UV_NATIVE_TLS=1 uv pip install -e ".[dev]"
.venv/bin/pytest -q && .venv/bin/ruff check . && .venv/bin/mypy src tests
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

## Not done yet

- Deny-all `firestore.rules` and the `transactions` composite index are not deployed to the real project
  (`firebase deploy --only firestore --config infra/firebase.emulator.json`). Without the index, `transactions_from_account` fails on real Firestore.
- Neo4j hosting for deployment is undecided; confirm policy defaults (weights 0.4/0.6, thresholds 30/60, 180 s hold).
- Old TypeScript prototype (`apps/banking-web`, `services/fraud-api`, `services/agents`) stays until task 7.3.
