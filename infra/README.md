# infra

## Local (Firestore emulator + Neo4j)

```bash
# Neo4j (bolt 7687, browser http://localhost:7474, user neo4j / trustbank-local-pw)
docker compose -f infra/docker-compose.yml up -d

# Firestore emulator on 127.0.0.1:8085
firebase emulators:start --only firestore --config infra/firebase.emulator.json --project trustbank-local
```

Config: copy `infra/.env.example` to `services/backend/.env`.

## Neo4j on GCP (shared, Singapore)

- VM `trustbank-neo4j`, zone `asia-southeast1-b`, e2-medium, Debian 12, project `project-b63ed173-f777-4777-81a`.
- Neo4j 5.26 Community in Docker, data on `/opt/neo4j/data`, restarts on boot. Created from `infra/vm-startup.sh`.
- Password lives only in instance metadata (`neo4j-password`) and, for the owner, in the gitignored `services/backend/.env.vm`.
- **No public database port.** The firewall rule `allow-iap-ssh` allows 22, 7687 and 7474 only from Google's IAP range, so you reach it through a tunnel:

```bash
export CLOUDSDK_PYTHON=/opt/homebrew/bin/python3.14
gcloud compute start-iap-tunnel trustbank-neo4j 7687 --local-host-port=localhost:7688 \
  --zone asia-southeast1-b --project project-b63ed173-f777-4777-81a
# browser UI (optional): same command with 7474 and localhost:7475
```

Then use `TRUSTBANK_NEO4J_URI=bolt://localhost:7688` and the VM password. Teammates need `roles/iap.tunnelResourceAccessor` and `roles/compute.viewer` on the project.

Cost: about US$25-30 a month while running. Stop it when idle:
`gcloud compute instances stop trustbank-neo4j --zone asia-southeast1-b` (data persists on the disk).

For Cloud Run later: connect through Direct VPC egress to the VM's internal IP (10.148.0.2) and add a firewall rule for 7687 from the Cloud Run subnet. That is task 7.2.
