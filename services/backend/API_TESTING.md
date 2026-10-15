# Run and test the backend by hand

All commands assume the repo root unless a `cd` is shown. Data is synthetic.

## 1. One-time setup

```bash
cd services/backend
uv venv --python /opt/homebrew/bin/python3.14 .venv       # 3.12 download is blocked by corporate TLS
unset SSL_CERT_FILE; UV_NATIVE_TLS=1 uv pip install -e ".[dev]"
cp ../../infra/.env.example .env
```

Edit `services/backend/.env` (gitignored; never commit it):

```
TRUSTBANK_ENVIRONMENT=local
TRUSTBANK_GOOGLE_CLOUD_PROJECT=project-b63ed173-f777-4777-81a   # real Firestore
TRUSTBANK_TOKEN_SECRET=<openssl rand -hex 32>
TRUSTBANK_INVESTIGATOR_CODE=<any code you choose>
TRUSTBANK_NEO4J_URI=bolt://localhost:7687
TRUSTBANK_NEO4J_USER=neo4j
TRUSTBANK_NEO4J_PASSWORD=trustbank-local-pw
```

The service refuses to start if the token secret (32+ characters) or investigator code is missing.
Leave `TRUSTBANK_FIRESTORE_EMULATOR_HOST` unset to use real Firestore.

## 2. Prerequisites for each run

1. **Google credentials** for the project owner (`teamdynaminds3@gmail.com`):
   `gcloud auth application-default login` (use an incognito window if the wrong account is picked).
   Run gcloud with `export CLOUDSDK_PYTHON=/opt/homebrew/bin/python3.14`.
2. **Neo4j running locally:** `docker compose -f infra/docker-compose.yml up -d` (browser: http://localhost:7474).
3. **Data loaded** (only needed once, or to refresh timestamps before a demo):

```bash
cd services/backend
P=project-b63ed173-f777-4777-81a
.venv/bin/python -m trustbank.seed --remote $P --reset --yes
.venv/bin/python -m trustbank.ingest --reset --remote-firestore $P
```

## 3. Start the API

```bash
cd services/backend
.venv/bin/uvicorn --factory trustbank.main:create_app --port 8000
```

Interactive docs: http://localhost:8000/docs

## 4. Test with curl

Open a second terminal at the repo root.

```bash
B=http://localhost:8000/api/v1
H='content-type: application/json'
CODE=$(grep '^TRUSTBANK_INVESTIGATOR_CODE=' services/backend/.env | cut -d= -f2)
tok() { python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'; }
```

### Public

```bash
curl -s $B/health      # {"status":"ok","firestore":..,"neo4j":..,"model":{"status":"not_configured"}}
curl -s $B/personas    # Asha Menon, Priya Nair
```

### Customer

```bash
CT=$(curl -s -XPOST $B/auth/customer -H "$H" -d '{"persona_id":"cust_asha"}' | tok)   # or cust_priya
curl -s $B/me -H "Authorization: Bearer $CT"                                          # balance, last 5 payments
curl -s "$B/recipients/lookup?q=nova.trade@trustpay" -H "Authorization: Bearer $CT"   # by UPI id
curl -s "$B/recipients/lookup?q=500074059712" -H "Authorization: Bearer $CT"          # by account number
curl -s "$B/recipients/lookup?q=nobody@upi" -H "Authorization: Bearer $CT"            # {"found":false,...}
```

Other handles to try: `rahul.verma@trustpay`, `sharma.store@trustpay`, `ananya.rao@trustpay`, `freshmart@trustpay`.

### Investigator

```bash
IT=$(curl -s -XPOST $B/auth/investigator -H "$H" -d "{\"code\":\"$CODE\"}" | tok)
curl -s $B/investigation/session -H "Authorization: Bearer $IT"                       # {"role":"investigator"}
```

### Expected failures

```bash
curl -s -w ' %{http_code}\n' $B/me                                                    # 401
curl -s -w ' %{http_code}\n' $B/investigation/session -H "Authorization: Bearer $CT"  # 403 customer on investigator route
curl -s -w ' %{http_code}\n' $B/me -H "Authorization: Bearer $IT"                     # 403 investigator on customer route
curl -s -w ' %{http_code}\n' -XPOST $B/auth/customer -H "$H" -d '{"persona_id":"x"}' # 404
curl -s -w ' %{http_code}\n' "$B/recipients/lookup?q=hello" -H "Authorization: Bearer $CT"  # 422
for i in 1 2 3 4 5 6; do
  curl -s -o /dev/null -w "%{http_code} " -XPOST $B/auth/investigator -H "$H" -d '{"code":"bad"}'
done; echo                                                                            # 401 x5, then 429
```

After the 429, wait 60 seconds before logging in as investigator again. Every error body is
`{"error":{"code","message","requestId"}}`; the same id appears in the server log line.

## 5. Try the anomaly agent (no HTTP endpoint yet)

Run from `services/backend`:

```bash
.venv/bin/python - <<'E'
import asyncio
from datetime import datetime, UTC
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from trustbank.agents.anomaly import build_anomaly_agent, STATE_INPUT, STATE_FINDING
from trustbank.config import get_settings
from trustbank.store import DatasetRepository, create_client

repo = DatasetRepository(create_client(get_settings()))
CASES = [  # (customer, beneficiary, amount)
    ("cust_asha", "ben_rahul", 2500),         # about 0
    ("cust_asha", "ben_heritage", 40000),     # about 90
    ("cust_priya", "ben_novatrade", 8000),    # about 70, uncapped (65% of balance)
    ("cust_priya", "ben_sharma_store", 400),  # low, capped, low confidence
    ("cust_nobody", "ben_rahul", 100),        # FAILED
]
async def main():
    svc = InMemorySessionService()
    r = Runner(app_name="t", agent=build_anomaly_agent(repo), session_service=svc)
    for c, b, a in CASES:
        s = await svc.create_session(app_name="t", user_id="u", state={STATE_INPUT: {
            "customer_id": c, "beneficiary_id": b, "amount": a,
            "as_of": datetime.now(UTC).isoformat()}})
        async for _ in r.run_async(user_id="u", session_id=s.id,
                new_message=types.Content(role="user", parts=[types.Part(text="go")])): pass
        f = (await svc.get_session(app_name="t", user_id="u", session_id=s.id)).state[STATE_FINDING]
        print(c, b, a, "->", f["status"], f["score"], f["confidence"])
        for e in f["evidence"]: print("   ", e["id"], e["points"], "|", e["summary"])
        if f["error"]: print("    error:", f["error"])
asyncio.run(main())
E
```

## 6. Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `no such file or directory: .venv/bin/python` | You are not in `services/backend`. |
| Startup `ValidationError` about secrets | Fill `TRUSTBANK_TOKEN_SECRET` and `TRUSTBANK_INVESTIGATOR_CODE` in `.env`. |
| `/health` shows `neo4j: unavailable` | Start Docker Neo4j, or open the IAP tunnel if using the VM (`infra/README.md`). |
| `/health` shows `firestore: unavailable`, or 403 | ADC is the wrong account. Re-run `gcloud auth application-default login` as the owner. |
| `/me` returns 503 mentioning an index | The `transactions` composite index is missing (it exists on the real project; create it on a new one). |
| uv install fails with TLS errors | `unset SSL_CERT_FILE; UV_NATIVE_TLS=1 uv pip install ...` |
