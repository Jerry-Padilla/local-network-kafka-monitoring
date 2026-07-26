# Local deployment

## Prerequisites

Install Docker Desktop/Engine with Compose v2. A local Python installation,
Java, Kafka, PostgreSQL, and Make are not required for the Docker-first path.

Copy `.env.example` to `.env` and replace the two sample passwords. Do not
commit `.env`.

## Startup

`./scripts/netpulse.ps1 up` on Windows or `make up`/`./scripts/netpulse.sh up`
on a POSIX host builds images and starts PostgreSQL, Kafka, topic
reconciliation, Alembic migration, and the ingestor. Compose waits for
dependency health and one-shot initialization jobs.

Only Kafka port 29092 and PostgreSQL port 5432 are published, both on
`127.0.0.1`. Container-to-container traffic uses the `backend` network.

Persistent volumes are:

- `netpulse_kafka-data`
- `netpulse_postgres-data`

Normal `down` preserves them. `reset` removes them and all local demo data.

## Validation

```text
./scripts/netpulse.ps1 config
./scripts/netpulse.ps1 lint
./scripts/netpulse.ps1 typecheck
./scripts/netpulse.ps1 test
./scripts/netpulse.ps1 test-integration
./scripts/netpulse.ps1 demo
./scripts/netpulse.ps1 verify
```

The verification command requires both agents, typed measurements, no duplicate
raw `event_id`, and a successful query connection. Integration tests also prove
malformed-record evidence and dead-letter acknowledgement.

## Configuration

Compose reads `.env`. Services use:

- `KAFKA_BOOTSTRAP_SERVERS`
- `NETPULSE_DATABASE_URL`
- `NETPULSE_ADMIN_DATABASE_URL` for the one-shot migration only
- `NETPULSE_CONSUMER_GROUP`
- `NETPULSE_MAX_PROCESSING_ATTEMPTS`
- `NETPULSE_RETRY_BASE_SECONDS`
- `NETPULSE_DELIVERY_TIMEOUT_SECONDS`
- `NETPULSE_LOG_LEVEL`
- `NETPULSE_SIMULATOR_SEED`

The application connects as limited role `netpulse_app`; only migrations use
the database administrator.
