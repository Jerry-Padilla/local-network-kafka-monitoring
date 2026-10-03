# Phase 6 — daily reliability query API design

## Intent and boundary

Finish NetPulse v1 with a stable, read-only HTTP interface for daily network
reliability. The API is for the local operator and portfolio demonstrations: a
client can retrieve bounded pages of the same daily aggregates already exposed
by `v_daily_probe_reliability` without receiving database credentials or SQL
access.

V1 exposes daily reliability only. Incident summaries, live measurements, SRE
agent or pipeline status, write operations, arbitrary SQL, authentication,
public or private-LAN exposure, and Kubernetes deployment remain later work.
The API is complete when it has a versioned contract, least-privilege database
access, deterministic pagination, validation and failure behavior, local
Compose deployment, tests, and accurate operator documentation.

## Considered approaches

### Separate query service — selected

Add `services/query-api` as a small FastAPI service with its own configuration,
models, cursor codec, repository, application factory, container, and tests.
This preserves the analytics job as a one-shot writer, gives the HTTP process an
independent lifecycle and read-only identity, and creates a clean boundary for
future API versions. It adds one image and one Compose service, but that cost is
appropriate for a long-running network service.

### Add HTTP serving to the analytics package

This would reuse the existing package and database dependency with fewer new
files. It would also couple a one-shot, write-capable refresh job to a
long-running, read-only server and make deployment credentials and process
lifecycle harder to reason about. That coupling is rejected.

### Expose PostgreSQL through a generated data API

A generated REST or GraphQL layer could reduce application code. It would add a
new infrastructure dependency, make the public contract follow database
details, and complicate query limits and pagination. That is unnecessary for
one deliberately narrow endpoint and is rejected.

## Architecture

`services/query-api` is an independent Python 3.12 package named
`netpulse-query-api`. Uvicorn runs a FastAPI application factory. The service
opens a bounded psycopg connection pool during application startup and closes
it during shutdown. Its repository executes fixed, parameterized SQL against
`v_daily_probe_reliability`; no request value can select a table, column, or SQL
fragment.

The service joins the existing Compose `backend` network under a new opt-in
`api` profile. Container port 8000 is published as `127.0.0.1:8000`, never as a
wildcard or LAN binding. The container runs as the existing non-root NetPulse
UID/GID convention and has a health check against its database-aware health
endpoint.

An idempotent provisioning step creates or rotates a dedicated LOGIN role,
`netpulse_query_api`, and grants it membership in the existing NOLOGIN role
`netpulse_report`. The query service receives only that login's connection
string. It never receives `netpulse_app` or administrator credentials. The
password is supplied through `.env`; only its variable name and an explicitly
local development default appear in the repository. Provisioning works with an
existing PostgreSQL volume and does not require destroying data.

## HTTP contract

### Health

`GET /healthz` executes `SELECT 1` through the pool. It returns HTTP 200 with
`{"status":"ok"}` when the service can reach PostgreSQL. Pool exhaustion,
connection failure, or a failed probe returns HTTP 503 with
`{"detail":"database unavailable"}`. The response does not expose hosts,
credentials, SQL text, or driver exceptions.

### Daily reliability

`GET /v1/reliability/daily` returns a page with this shape:

```json
{
  "items": [],
  "next_cursor": null,
  "limit": 50
}
```

Each item contains every stable aggregate from
`v_daily_probe_reliability`: `date_utc`, `agent_id`, `endpoint_id`,
`source_kind`, `probe_type`, `total_count`, `success_count`, `failure_count`,
`success_rate_pct`, `latency_count`, `latency_sum_ms`, `mean_latency_ms`,
`packet_loss_count`, `packet_loss_sum_pct`, and `mean_packet_loss_pct`. Dates
use ISO 8601 `YYYY-MM-DD`. Counts are JSON integers; rates, sums, and means are
JSON numbers or `null` when the source view reports no measurement.

Supported query parameters are:

- `from_date` and `through_date`, inclusive ISO dates. They must be supplied
  together or both omitted. `from_date` must not follow `through_date`, and the
  inclusive span must not exceed 366 days.
- `agent_id`, `endpoint_id`, and `probe_type`, each an exact, case-sensitive,
  nonempty match with a maximum length of 128 characters.
- `source_kind`, restricted to `network_measurement` or `service_check`.
- `limit`, default 50 and restricted to 1 through 200.
- `cursor`, an opaque continuation token returned by the preceding response.

Unknown query parameters are rejected so misspelled filters cannot silently
produce broader results. The endpoint does not calculate a total count; doing
so would add an unbounded second query without helping cursor traversal.

Results are ordered by `date_utc` descending, then `agent_id`, `endpoint_id`,
`source_kind`, and `probe_type` ascending. The repository fetches `limit + 1`
rows and returns a cursor only when another page exists. It uses keyset
pagination, not offset pagination, so runtime and duplicate/skip behavior do
not degrade with page depth.

The cursor is URL-safe base64 encoding of a versioned JSON payload containing
the last row's complete ordering key and a SHA-256 fingerprint of the effective
filters. It is an opaque navigation token, not an authorization boundary.
Decoding enforces a maximum token length, the schema and version, valid field
types, and the filter fingerprint. Malformed, obsolete, or filter-mismatched
cursors are rejected rather than interpreted. All decoded values still reach
SQL only as bound parameters.

FastAPI publishes the versioned schema at `/openapi.json` and interactive local
documentation at `/docs`. No CORS origins are enabled. Application metadata
identifies the API as NetPulse Query API v1.

## Components and responsibilities

- `config` loads the database URL, pool bounds, statement/acquisition timeouts,
  and log level from environment variables and rejects missing or unsafe
  values. Network publishing remains fixed in Compose rather than being an
  application environment option.
- `models` owns response schemas and the two allowed source kinds.
- `cursor` encodes and validates versioned keyset cursors independently of HTTP
  and PostgreSQL.
- `repository` owns the fixed SQL, health probe, typed row conversion, and
  `limit + 1` pagination result.
- `api` validates query parameters, constructs effective filters, maps domain
  and dependency failures to HTTP responses, and returns typed models.
- `main` builds the application, manages the pool lifespan, configures
  structured logging, and is the Uvicorn entry point.

These boundaries keep pagination rules testable without a database, query
semantics testable without an HTTP server, and the HTTP contract testable with
a fake repository.

## Data and request flow

1. FastAPI parses the request and rejects unknown, empty, overlong, or
   contradictory parameters.
2. The cursor codec validates the token and confirms that its filter
   fingerprint matches the current request.
3. The repository acquires a pooled read-only connection, sets a bounded
   statement timeout, and executes one parameterized query against
   `v_daily_probe_reliability` for at most 201 rows.
4. The repository converts database rows into domain records. The API returns
   at most the requested limit and derives `next_cursor` from the last returned
   row only when an additional row was fetched.
5. A structured completion log records status, duration, returned row count,
   and a generated request ID. It excludes credentials, raw cursor content,
   database exception text, agent IDs, endpoint IDs, and filter values.

Connections are transaction-read-only and use a configurable statement
timeout with a conservative local default. Pool size and acquisition timeout
are bounded so traffic cannot create unbounded PostgreSQL connections or wait
forever.

## Errors and operational behavior

FastAPI validation failures, invalid filter combinations, and invalid cursors
return HTTP 422 with a stable error detail. An empty result is HTTP 200 with an
empty `items` array and a null cursor. PostgreSQL connection failures, pool
timeouts, and statement timeouts return HTTP 503 with the generic detail
`database unavailable`. Unexpected server errors return HTTP 500 with
`internal server error`; full exceptions are confined to structured server
logs and are scrubbed of connection strings.

Every response includes `X-Request-ID`. A caller-supplied request ID is accepted
only when it is printable ASCII and at most 128 characters; otherwise the
service generates a UUID. Shutdown stops accepting work, lets Uvicorn complete
its normal graceful window, and closes the database pool.

The application does not cache query results. Freshness is exactly the
freshness of the analytics refresh that populates `fact_reliability_daily`.
Documentation must state that the API does not trigger analytics refreshes and
does not claim real-time data.

## Privacy and security boundary

The endpoint returns aggregates and stable identifiers from the reporting view
only. It does not return raw probe events, target addresses, SSIDs, BSSIDs,
payloads, credentials, exception messages, incident evidence, or operational
tables. Database grants are the primary data boundary; application SQL is a
second boundary. Tests prove the API identity can select the approved view and
cannot select base telemetry or mutate analytics data.

Localhost-only publishing is the v1 access control. There is no API key or user
authentication, so documentation must warn operators not to change the bind
address or proxy the service onto a LAN or public interface. Any broader
exposure requires a later design adding authentication, authorization, TLS,
rate limiting, and a reviewed privacy model.

## Testing and acceptance

Development follows test-driven implementation. Unit and contract tests cover:

- required configuration, safe defaults, invalid pool and timeout settings,
  and database URL redaction;
- response serialization, nullable measurements, filter limits, unknown
  parameters, inclusive date rules, and the 366-day bound;
- cursor round trips, version rejection, length limits, malformed payloads,
  filter mismatch, and pagination across identical dates;
- fixed parameterized SQL, deterministic mixed-direction ordering,
  `limit + 1`, correct next-page behavior, and typed database rows;
- success, empty results, validation responses, request IDs, generic 500/503
  responses, health behavior, and OpenAPI paths;
- Compose profile, loopback port binding, non-root container, health check,
  dependency ordering, and absence of write-capable credentials;
- idempotent role provisioning and committed-secret checks.

Database integration tests apply current migrations, provision the API login,
query a seeded page through HTTP, follow its cursor without duplicate keys, and
verify filtering and JSON types. Privilege tests prove the login can select
`v_daily_probe_reliability` while base telemetry reads and all writes fail.
`EXPLAIN` acceptance confirms the paginated query uses the
`fact_reliability_daily` primary-key index for the unfiltered and date-bounded
paths; if PostgreSQL cannot do so through the view, a migration adds only the
specific supporting index demonstrated necessary by the captured plan.

The final verification runs the full feasible Python unit suite, coverage,
Ruff formatting and linting, strict mypy, Compose configuration for all
profiles, database migration tests, query API integration tests, container
health, and a manual two-page curl demonstration. Results must report exact
commands, passes, deselections, environmental limitations, and any unavailable
physical-Pi checks without converting them into success claims.

## Documentation and release boundary

Add an operator guide covering environment setup, starting the `api` profile,
refreshing analytics, health and query examples, pagination, errors, freshness,
least-privilege provisioning, and localhost-only security. Link it from the
README and mark roadmap Phase 6 complete only after the implementation and
acceptance evidence are green.

V1 is then the completed local product boundary: collection, durable ingestion,
streaming curation, incident classification, dimensional daily analytics,
operational dashboards, and a supported daily reliability query API. The next
cycle may design incident, live-measurement, and SRE-status resources without
changing this `/v1/reliability/daily` contract.
