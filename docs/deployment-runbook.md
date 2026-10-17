# TrustBank deployment runbook

This runbook deploys the Python FastAPI backend to Cloud Run in `asia-southeast1`.
Firebase Hosting serves the Angular application and rewrites `/api/**` to that Cloud Run service.
All data is synthetic; payments and PINs remain simulated.

## Deployment topology

```text
Browser
  -> Firebase Hosting (Angular)
       -> /api/** rewrite
            -> Cloud Run: trustbank-api
                 -> Firestore (system of record)
                 -> Neo4j VM over VPC egress
                 -> Gemini API through ADK
```

The anomaly and fraud-network agents execute inside the Cloud Run container. The
questionnaire and explainer execute in that same container and call Gemini with a custom API key.
No agent is deployed as a separate service.

## Current state

- Target project: `project-b63ed173-f777-4777-81a`
- Target API region: `asia-southeast1`
- Firebase Hosting site: `trustbank-pausepay`
- Neo4j VM private address: `10.148.0.2:7687`
- Existing `services/Dockerfile` is for superseded Node services. Build current backend from
  `services/backend/Dockerfile`.

Do not store secrets in this repository, shell history, committed `.env` files, or Cloud Build
substitutions. Commands below use Secret Manager references.

## Deployment record

| Checkpoint | Status | Evidence |
|---|---|---|
| Deployment assets prepared | Complete | Python Dockerfile, Docker build exclusions, Firebase rewrite, and this runbook were added locally. |
| Local container build | Complete | `docker build --tag trustbank-backend:local services/backend` completed successfully on 2026-10-16. |
| Cloud Run deployment | Complete | Revision `trustbank-api-00004-4tl` is ready in `asia-southeast1` at `https://trustbank-api-gpusuyb6jq-as.a.run.app`. |
| Firestore runtime access | Complete | Deployed `/health` reports `firestore: ok`. |
| Cloud Run to Neo4j firewall | Complete | Firewall rule `allow-trustbank-run-to-neo4j` allows TCP 7687 from `10.8.0.0/28` to VM instances tagged `trustbank-neo4j`. |
| Cloud Run to Neo4j network path | Complete | Connector is `READY` on `default` with `10.8.0.0/28`; Cloud Run attaches it with private-ranges egress; VM `10.148.0.2` is running, tagged, and listens on TCP 7687. |
| Neo4j runtime access | Complete | After rotating the Neo4j password secret and creating a new Cloud Run revision, deployed `/health` reports `neo4j: ok`. |
| Synthetic graph ingestion | Complete | Reset and ingestion completed with integrity checks: 22 customers, 15 beneficiaries, 37 accounts, 279 transactions, and 2 declared connections. |
| Gemini API-key configuration | Complete | Revision `trustbank-api-00004-4tl` injects `GOOGLE_API_KEY` from Secret Manager and sets `GOOGLE_GENAI_USE_VERTEXAI=FALSE`. |
| Gemini model health | Complete | `/health` reports `model: unchecked` by design. A live S8 payment through `https://trustbank-pausepay.web.app/api/v1` on 2026-10-17 ran the questionnaire and explainer on `gemini-3.8-flash` with no fallbacks and reached `HOLD_ACTIVE`. |
| Web hosting | Complete | Firebase Hosting site `trustbank-pausepay` serves the Angular app at `https://trustbank-pausepay.web.app` and rewrites `/api/**` to Cloud Run. |
| Neo4j hosting decision | Decided | Self-hosted Neo4j 5 Community on a private GCE VM (`trustbank-neo4j`), reached from Cloud Run over a VPC connector; no public port. Chosen over AuraDB to keep data in-project and cost near US$25-30 a month. Stop the VM when idle. |

## Checkpoint 0: local readiness

Run from repository root:

```bash
git status --short
cd services/backend
.venv/bin/ruff check .
.venv/bin/mypy src tests
.venv/bin/pytest -q
docker build --tag trustbank-backend:local .
```

To start a container locally, first start its required dependencies:

```bash
docker compose -f ../../infra/docker-compose.yml up -d
firebase emulators:start --only firestore \
  --config ../../infra/firebase.emulator.json \
  --project trustbank-local
```

Then, in another terminal:

```bash
docker run --rm -p 8080:8080 \
  -e TRUSTBANK_ENVIRONMENT=test \
  -e TRUSTBANK_GOOGLE_CLOUD_PROJECT=trustbank-local \
  -e TRUSTBANK_FIRESTORE_EMULATOR_HOST=host.docker.internal:8085 \
  -e TRUSTBANK_NEO4J_URI=bolt://host.docker.internal:7687 \
  -e TRUSTBANK_TOKEN_SECRET=test-token-secret-not-for-production \
  -e TRUSTBANK_INVESTIGATOR_CODE=test-investigator-code \
  trustbank-backend:local
```

Finally:

```bash
curl --fail http://127.0.0.1:8080/health
```

**Success criteria**

- Ruff and mypy exit successfully.
- All non-live backend tests pass.
- Container starts and `/health` returns HTTP 200.

**Current status:** The backend suite passes (113 tests with Neo4j running; Firestore-emulator tests skip when the emulator is down). Restaurant graph-flow coverage is still tracked in OpenSpec task 1.7.

Stop the local container with `Ctrl-C`.

## Checkpoint 1: authenticate and inspect project

```bash
export PROJECT_ID=project-b63ed173-f777-4777-81a
export REGION=asia-southeast1
export SERVICE=trustbank-api
export REPOSITORY=trustbank

gcloud auth login
gcloud auth application-default login
gcloud config set project "$PROJECT_ID"
gcloud projects describe "$PROJECT_ID" --format='value(projectNumber,projectId)'
gcloud auth list
firebase use "$PROJECT_ID"
```

**Success criteria**

- Active Google account is authorized for this project.
- Active Firebase project is `project-b63ed173-f777-4777-81a`.
- Do not continue if account or project differs from intended target.

## Checkpoint 2: enable required Google Cloud APIs

```bash
gcloud services enable \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  run.googleapis.com \
  secretmanager.googleapis.com \
  vpcaccess.googleapis.com \
  firestore.googleapis.com
```

**Success criteria**

```bash
gcloud services list --enabled \
  --filter='config.name:(artifactregistry.googleapis.com cloudbuild.googleapis.com run.googleapis.com secretmanager.googleapis.com vpcaccess.googleapis.com firestore.googleapis.com)' \
  --format='value(config.name)'
```

Output includes every requested API.

## Checkpoint 3: create Artifact Registry repository

```bash
gcloud artifacts repositories describe "$REPOSITORY" \
  --location="$REGION" \
  || gcloud artifacts repositories create "$REPOSITORY" \
       --repository-format=docker \
       --location="$REGION" \
       --description='TrustBank container images'
```

**Success criteria**

```bash
gcloud artifacts repositories describe "$REPOSITORY" \
  --location="$REGION" \
  --format='value(name,format)'
```

Expected format: `DOCKER`.

## Checkpoint 4: create dedicated Cloud Run service account

```bash
export RUNTIME_SA=trustbank-api-runtime
export RUNTIME_SA_EMAIL="${RUNTIME_SA}@${PROJECT_ID}.iam.gserviceaccount.com"

gcloud iam service-accounts describe "$RUNTIME_SA_EMAIL" \
  || gcloud iam service-accounts create "$RUNTIME_SA" \
       --display-name='TrustBank API runtime'

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA_EMAIL}" \
  --role='roles/datastore.user'
```

**Success criteria**

```bash
gcloud projects get-iam-policy "$PROJECT_ID" \
  --flatten='bindings[].members' \
  --filter="bindings.members:serviceAccount:${RUNTIME_SA_EMAIL}" \
  --format='table(bindings.role)'
```

Output includes `roles/datastore.user`.

## Checkpoint 5: store runtime secrets

Generate strong values locally. Do not paste generated values into this document. These commands
are safe in zsh and create an enabled version whether the secret is new or already exists.

```bash
put_secret() {
  local name="$1" value="$2"
  if gcloud secrets describe "$name" >/dev/null 2>&1; then
    printf '%s' "$value" | gcloud secrets versions add "$name" --data-file=-
  else
    printf '%s' "$value" | gcloud secrets create "$name" \
      --replication-policy=automatic --data-file=-
  fi
}

TOKEN_SECRET="$(openssl rand -base64 48)"
printf 'Investigator demo access code: ' >&2
read -rs INVESTIGATOR_CODE; echo >&2
printf 'Neo4j password: ' >&2
read -rs NEO4J_PASSWORD; echo >&2
printf 'Gemini API key: ' >&2
read -rs GEMINI_API_KEY; echo >&2

[[ -n "$INVESTIGATOR_CODE" && -n "$NEO4J_PASSWORD" && -n "$GEMINI_API_KEY" ]] \
  || { echo 'A required secret was empty; stopping.' >&2; return 1; }

put_secret trustbank-token-secret "$TOKEN_SECRET"
put_secret trustbank-investigator-code "$INVESTIGATOR_CODE"
put_secret trustbank-neo4j-password "$NEO4J_PASSWORD"
put_secret trustbank-gemini-api-key "$GEMINI_API_KEY"

unset TOKEN_SECRET INVESTIGATOR_CODE NEO4J_PASSWORD GEMINI_API_KEY
unset -f put_secret
```

Grant runtime access:

```bash
for SECRET in trustbank-token-secret trustbank-investigator-code trustbank-neo4j-password trustbank-gemini-api-key; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --member="serviceAccount:${RUNTIME_SA_EMAIL}" \
    --role='roles/secretmanager.secretAccessor'
done
```

**Success criteria**

```bash
gcloud secrets list --filter='name:trustbank-' --format='table(name)'
```

Expected secrets: token secret, investigator code, Neo4j password, Gemini API key. Do not read or
print values.

## Checkpoint 6: create Serverless VPC Access connector

Choose an unused `/28` range in the target VPC before running this command. Replace
`10.8.0.0/28` if it overlaps any existing subnet.

```bash
export VPC_NETWORK=default
export CONNECTOR=trustbank-run-egress
export CONNECTOR_RANGE=10.8.0.0/28

gcloud compute networks vpc-access connectors describe "$CONNECTOR" \
  --region="$REGION" \
  || gcloud compute networks vpc-access connectors create "$CONNECTOR" \
       --region="$REGION" \
       --network="$VPC_NETWORK" \
       --range="$CONNECTOR_RANGE" \
       --min-instances=2 \
       --max-instances=3
```

Allow connector traffic to Neo4j only:

```bash
gcloud compute firewall-rules create allow-trustbank-run-to-neo4j \
  --network="$VPC_NETWORK" \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:7687 \
  --source-ranges="$CONNECTOR_RANGE" \
  --target-tags=trustbank-neo4j \
  || gcloud compute firewall-rules describe allow-trustbank-run-to-neo4j
```

**Success criteria**

```bash
gcloud compute networks vpc-access connectors describe "$CONNECTOR" \
  --region="$REGION" \
  --format='value(state)'
```

Expected state: `READY`.

The VM must carry network tag `trustbank-neo4j`. Add that tag before the firewall step if it is
absent:

```bash
gcloud compute instances add-tags trustbank-neo4j \
  --zone=asia-southeast1-b \
  --tags=trustbank-neo4j
```

## Checkpoint 7: build and inspect immutable image

```bash
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/trustbank-api:$(git rev-parse --short HEAD)"

gcloud builds submit services/backend --tag="$IMAGE"
gcloud artifacts docker images describe "$IMAGE"
```

**Success criteria**

- Cloud Build completes successfully.
- Artifact Registry reports image digest.
- Record image digest in deployment notes; deploy by digest for a production release.

## Checkpoint 8: deploy Cloud Run

```bash
gcloud run deploy "$SERVICE" \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="$RUNTIME_SA_EMAIL" \
  --allow-unauthenticated \
  --ingress=all \
  --vpc-connector="$CONNECTOR" \
  --vpc-egress=private-ranges-only \
  --min-instances=1 \
  --max-instances=1 \
  --cpu=1 \
  --memory=1Gi \
  --timeout=60 \
  --set-env-vars="TRUSTBANK_ENVIRONMENT=deployed,TRUSTBANK_GOOGLE_CLOUD_PROJECT=${PROJECT_ID},TRUSTBANK_NEO4J_URI=bolt://10.148.0.2:7687,TRUSTBANK_NEO4J_USER=neo4j,TRUSTBANK_MODEL_NAME=gemini-3.8-flash,GOOGLE_GENAI_USE_VERTEXAI=FALSE" \
  --set-secrets="TRUSTBANK_TOKEN_SECRET=trustbank-token-secret:latest,TRUSTBANK_INVESTIGATOR_CODE=trustbank-investigator-code:latest,TRUSTBANK_NEO4J_PASSWORD=trustbank-neo4j-password:latest,GOOGLE_API_KEY=trustbank-gemini-api-key:latest"

export API_URL="$(gcloud run services describe "$SERVICE" --region="$REGION" --format='value(status.url)')"
printf '%s\n' "$API_URL"
```

`min-instances=1` and `max-instances=1` keep in-process live SSE notifications reliable for demo
traffic. Persisted timeline events and polling remain fallback mechanisms. Use a shared event bus
before horizontally scaling live timeline delivery.

**Success criteria**

```bash
curl --fail --show-error "$API_URL/health"
gcloud run services describe "$SERVICE" --region="$REGION" \
  --format='table(status.url,status.conditions[0].status,status.latestReadyRevisionName)'
```

The health payload must report dependencies explicitly. Do not proceed while Firestore or Neo4j
is unavailable. `model: unchecked` is expected: health does not make a billable Gemini request.

## Checkpoint 9: seed and ingest synthetic data

Run this only after Cloud Run health and Neo4j network path succeed. Use a trusted operator
environment with access to Firestore and the private Neo4j VM.

```bash
cd services/backend
unset TRUSTBANK_FIRESTORE_EMULATOR_HOST
export TRUSTBANK_GOOGLE_CLOUD_PROJECT="$PROJECT_ID"
.venv/bin/python -m trustbank.seed --remote "$PROJECT_ID" --reset --yes

# In a separate terminal, keep an IAP tunnel open for local-to-VM Neo4j access:
gcloud compute start-iap-tunnel trustbank-neo4j 7687 \
  --local-host-port=localhost:7688 \
  --zone=asia-southeast1-b \
  --project="$PROJECT_ID"
```

With that tunnel still running, return to this terminal:

```bash
export TRUSTBANK_NEO4J_URI=bolt://localhost:7688
export TRUSTBANK_NEO4J_USER=neo4j
export TRUSTBANK_NEO4J_PASSWORD="$(gcloud secrets versions access latest \
  --secret=trustbank-neo4j-password)"
.venv/bin/python -m trustbank.graph.ingest --reset
unset TRUSTBANK_NEO4J_PASSWORD
```

**Success criteria**

- Seed command reports deterministic collection counts.
- Ingestion ends with `integrity: ok`.
- API can list personas and complete a low-risk synthetic payment.

## Checkpoint 10: connect Firebase Hosting

`firebase.json` must point its Cloud Run rewrite at `asia-southeast1`.

```bash
npm --prefix apps/banking-web ci
npm --prefix apps/banking-web run build
firebase deploy --only hosting
```

**Success criteria**

- Hosted application loads.
- `GET /api/v1/health` through Hosting succeeds.
- Persona login, low-risk payment, investigation access gate, and SSE/polling timeline work.

## Checkpoint 11: deploy Firestore browser-deny rules

Only backend service credentials should access Firestore.

```bash
firebase deploy --only firestore --config infra/firebase.emulator.json
```

**Success criteria**

- Firebase deployment reports rules and index status successfully.
- Browser cannot directly read Firestore.
- Cloud Run continues to read and write through its service account.

## Routine backend revision deployment

For ordinary backend code revisions, do not recreate Artifact Registry, the Cloud Run service,
runtime service account, secrets, VPC connector, firewall, Neo4j VM, Firestore, or Firebase
project.

```bash
cd services/backend
.venv/bin/ruff check .
.venv/bin/mypy src tests
.venv/bin/pytest -q

export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/trustbank-api:$(git rev-parse --short HEAD)"
gcloud builds submit . --tag="$IMAGE"
gcloud run deploy "$SERVICE" --image="$IMAGE" --region="$REGION"

export API_URL="$(gcloud run services describe "$SERVICE" \
  --region="$REGION" --format='value(status.url)')"
curl --fail --show-error "$API_URL/health"
gcloud run services describe "$SERVICE" --region="$REGION" \
  --format='table(status.latestReadyRevisionName,status.conditions[0].status)'
```

Health must report `firestore: ok` and `neo4j: ok`. `model: unchecked` is expected because
health does not make a billable Gemini call. Then test demo login, one low-risk payment, one
elevated-risk payment, and investigator timeline lookup.

| Change | Required additional work |
|---|---|
| Gemini API key rotation | Add a Secret Manager version, then create a new Cloud Run revision. |
| Neo4j password rotation | Update VM password and Secret Manager version together, then create a new Cloud Run revision. |
| Cloud Run environment variable or secret | Use `gcloud run services update`, then health and payment smoke tests. |
| Graph fixture, schema, or data change | Reseed Firestore and rerun Neo4j ingestion. Do not reset data for ordinary API changes. |
| Angular-only change | Build and run `firebase deploy --only hosting`; no backend revision needed. |
| Firebase rewrite/API region change | Verify Cloud Run, then deploy Hosting. |

## Verifying deployed Neo4j

Cloud Run health verifies deployed API-to-Neo4j connectivity:

```bash
curl --fail --show-error "$API_URL/health"
```

For direct VM graph verification, this read-only query prints only label counts and never exposes
the Neo4j password:

```bash
gcloud compute ssh trustbank-neo4j \
  --zone=asia-southeast1-b \
  --tunnel-through-iap \
  --command='PASSWORD="$(curl -fsS -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/attributes/neo4j-password)" && sudo docker exec trustbank-neo4j cypher-shell -u neo4j -p "$PASSWORD" "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS count ORDER BY label;"'
```

Expected seeded labels include `Account`, `Beneficiary`, `Customer`, and `Transaction`. Follow
with one graph-backed payment and investigation lookup to verify the complete Cloud Run,
Firestore, Neo4j, and API path.

## Rollback

List revisions:

```bash
gcloud run revisions list --service="$SERVICE" --region="$REGION"
```

Route all traffic to known-good revision:

```bash
gcloud run services update-traffic "$SERVICE" \
  --region="$REGION" \
  --to-revisions=REVISION_NAME=100
```

If Hosting was changed, deploy previous known-good frontend build. Do not delete Firestore,
Neo4j data, secrets, or Artifact Registry images during an incident.
