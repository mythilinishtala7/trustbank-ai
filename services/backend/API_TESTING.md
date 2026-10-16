# Run and test the backend by hand

All commands assume the repo root unless a `cd` is shown. Data is synthetic.

## 1. One-time setup

```bash
cd services/backend
uv venv --python /opt/homebrew/bin/python3.14 .venv
unset SSL_CERT_FILE; UV_NATIVE_TLS=1 uv pip install -e ".[dev]"
[ -f .env ] || cp ../../infra/.env.example .env
```

Python 3.14 is used because the 3.12 download is blocked by corporate TLS. If `services/backend/.env`
already exists, keep it: the template has empty secrets and points at the Firestore emulator.
The commands below carry `# comments`. In an interactive zsh run `setopt interactive_comments` once first,
or `#` is passed as an argument and the command fails.

Edit `services/backend/.env` (gitignored; never commit it):

```
TRUSTBANK_ENVIRONMENT=local
TRUSTBANK_GOOGLE_CLOUD_PROJECT=project-b63ed173-f777-4777-81a
TRUSTBANK_TOKEN_SECRET=<openssl rand -hex 32>
TRUSTBANK_INVESTIGATOR_CODE=<any code you choose>
TRUSTBANK_NEO4J_URI=bolt://localhost:7687
TRUSTBANK_NEO4J_USER=neo4j
TRUSTBANK_NEO4J_PASSWORD=trustbank-local-pw
```

The service refuses to start if the token secret (32+ characters) or investigator code is missing.
Do not set `TRUSTBANK_FIRESTORE_EMULATOR_HOST` when using real Firestore (the template sets it; delete that line).

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
tok() { python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])'; }
```

### Public

```bash
curl -s $B/health      # {"status":"ok","checks":{"firestore":"ok","neo4j":"ok","model":"unchecked"}}
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

## 5. Payment flow (runs the agents)

Needs `$CT` from section 4. Recipient is a UPI id or account number, not a beneficiary id.
`POST /payments` runs the anomaly and network agents, so it can take 10 to 30 seconds.

```bash
P=$(curl -s -XPOST $B/payments -H "Authorization: Bearer $CT" -H "$H" -H "Idempotency-Key: demo-$RANDOM" \
  -d '{"recipient":"heritage.jewellers@trustpay","amount":40000}')
echo $P                                  # status QUESTIONNAIRE or PROCEEDING; note the "id"
ID=$(echo $P | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
curl -s $B/payments/$ID -H "Authorization: Bearer $CT"
# answer using the question ids and option values returned above
curl -s -XPOST $B/payments/$ID/answers -H "Authorization: Bearer $CT" -H "$H" \
  -d '{"answers":[{"questionId":"source_of_details","option":"messaging_app"}]}'
curl -s -XPOST $B/payments/$ID/acknowledge -H "Authorization: Bearer $CT"   # review outcome
curl -s -XPOST $B/payments/$ID/verify      -H "Authorization: Bearer $CT"
curl -s -XPOST $B/payments/$ID/continue    -H "Authorization: Bearer $CT"
curl -s -XPOST $B/payments/$ID/authorize   -H "Authorization: Bearer $CT" -H "$H" -d '{"pin":"1234"}'
curl -s -XPOST $B/payments/$ID/cancel      -H "Authorization: Bearer $CT"
```

Which actions are valid comes from the `actions` array of each response; others return 409.
A held payment cannot be authorised until the server-side hold expires.

Scenarios: Asha to `nova.trade@trustpay` 25000 (network), Priya to `nova.trade@trustpay` 8000,
Asha to `heritage.jewellers@trustpay` 40000 (anomaly only, never a hold).

Investigator (needs `$IT`):

```bash
curl -s $B/investigation/transactions -H "Authorization: Bearer $IT"
curl -s $B/investigation/transactions/$ID -H "Authorization: Bearer $IT"
curl -s $B/investigation/transactions/$ID/timeline -H "Authorization: Bearer $IT"
curl -N $B/investigation/transactions/$ID/events -H "Authorization: Bearer $IT"   # SSE
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
