# Daily reliability query API v1

The optional query API serves the daily analytics reporting view over HTTP. It
is intended for local, read-only exploration of refreshed facts.

> **Security:** v1 has no HTTP authentication. The published API port must
> remain bound to `127.0.0.1`. Do not publish it on a LAN or public interface.

## Prepare and operate

Copy `.env.example` to `.env` and set distinct local PostgreSQL admin, app,
and `QUERY_API_POSTGRES_PASSWORD` values. Keep `.env` private. Docker Compose
publishes the API only at `http://127.0.0.1:8000`; the API container receives
the dedicated login as separate environment components and encodes its own
database URL at startup.

Run the daily analytics refresh after ingestion and before expecting new rows:

```powershell
./scripts/netpulse.ps1 analytics-all
./scripts/netpulse.ps1 api-up
./scripts/netpulse.ps1 api-verify
./scripts/netpulse.ps1 api-down
```

On POSIX hosts, use `./scripts/netpulse.sh` with the same commands, or
`make analytics-all`, `make api-up`, `make api-verify`, and `make api-down`.
`api-build` builds the migration and API images without starting them.
`api-up` starts PostgreSQL, upgrades to migration `0008`, reruns the
`query-api-init` role provisioner, and waits for a healthy API. `api-verify`
checks `/healthz`, reads one bounded page with `limit=1`, and follows one
cursor if present. Its output contains only health and row counts. `api-down`
stops and removes only `query-api` and `query-api-init`; it keeps PostgreSQL,
other services, and named volumes.

For the live HTTP, privilege, and index-plan acceptance gate, run:

```bash
docker compose --profile api --profile test run --rm -e NETPULSE_INTEGRATION=1 \
  tests -p no:cacheprovider tests/test_query_api_integration.py -q
```

## Requests and responses

The API has `GET /healthz` and `GET /v1/reliability/daily`. A healthy response
is `{"status":"ok"}`. Check it with:

```bash
curl 'http://127.0.0.1:8000/healthz'
```

For a filtered page:

```bash
curl --get 'http://127.0.0.1:8000/v1/reliability/daily' \
  --data-urlencode 'from_date=2026-10-01' \
  --data-urlencode 'through_date=2026-10-02' \
  --data-urlencode 'source_kind=network_measurement' \
  --data-urlencode 'limit=25'
```

`from_date` and `through_date` are inclusive UTC dates and must be supplied
together, in order, within a 366-day span. Optional exact-match filters are
`agent_id`, `endpoint_id`, `source_kind` (`network_measurement` or
`service_check`), and `probe_type`. `limit` defaults to 50 and accepts 1–200.
Without filters, the endpoint returns the latest facts first, ordered by UTC
date descending, then agent, endpoint, source kind, and probe type ascending.

The response contains `items`, `next_cursor`, and `limit`. Each item has the
five ordering fields plus `total_count`, `success_count`, `failure_count`,
`success_rate_pct`, `latency_count`, `latency_sum_ms`, `mean_latency_ms`,
`packet_loss_count`, `packet_loss_sum_pct`, and `mean_packet_loss_pct`. Counts
are JSON integers. A mean or sum is JSON `null` when no applicable measurement
exists; it does not mean zero. To fetch the next page, repeat the *same*
filters and pass the previous `next_cursor` as `cursor`. Treat that cursor as
opaque; do not decode, log, or edit it. A `null` cursor means no further page.

HTTP 200 means a successful health or query response. Invalid filters,
duplicate or unknown query parameters, invalid limits, and mismatched or
malformed cursors return 422. Database unavailability returns 503. An
unexpected server error returns 500. These errors do not expose SQL or
database credentials.

The API reads `v_daily_probe_reliability` through the dedicated
`netpulse_query_api` database login. That login inherits reporting-view SELECT
permission and cannot read or mutate operational base tables. The API does
not perform analytics refreshes. Its results reflect the most recent
successful batch refresh for each date, not live network state. New events or
late arrivals need another `analytics-all` run or a selected-date refresh;
an empty result can mean that analytics has not yet run. Probe success rate
is not a network availability SLA.
