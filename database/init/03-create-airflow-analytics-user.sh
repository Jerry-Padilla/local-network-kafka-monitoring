#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${AIRFLOW_NETPULSE_DB_PASSWORD:-}" ]]; then
  echo "AIRFLOW_NETPULSE_DB_PASSWORD must be set" >&2
  exit 1
fi

psql_args=(
  --set ON_ERROR_STOP=1
  --username "$POSTGRES_USER"
  --dbname "$POSTGRES_DB"
  --set airflow_password="$AIRFLOW_NETPULSE_DB_PASSWORD"
)
if [[ -n "${PGHOST:-}" ]]; then
  psql_args+=(--host "$PGHOST")
fi

psql "${psql_args[@]}" <<'SQL'
SELECT format('CREATE ROLE netpulse_airflow LOGIN PASSWORD %L', :'airflow_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_airflow')
\gexec

SELECT format('ALTER ROLE netpulse_airflow LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT PASSWORD %L', :'airflow_password')
\gexec

SELECT format('REVOKE %I FROM netpulse_airflow GRANTED BY %I', parent.rolname, grantor.rolname)
FROM pg_auth_members AS membership
JOIN pg_roles AS parent ON parent.oid = membership.roleid
JOIN pg_roles AS member ON member.oid = membership.member
JOIN pg_roles AS grantor ON grantor.oid = membership.grantor
WHERE member.rolname = 'netpulse_airflow'
\gexec

REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM netpulse_airflow;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM netpulse_airflow;
REVOKE ALL PRIVILEGES ON SCHEMA public FROM netpulse_airflow;
GRANT USAGE ON SCHEMA public TO netpulse_airflow;

GRANT SELECT ON public.agents TO netpulse_airflow;
GRANT SELECT ON public.endpoints TO netpulse_airflow;
GRANT SELECT ON public.network_measurements TO netpulse_airflow;
GRANT SELECT ON public.service_checks TO netpulse_airflow;
GRANT SELECT ON public.agent_heartbeats TO netpulse_airflow;
GRANT SELECT ON public.raw_events TO netpulse_airflow;
GRANT SELECT ON public.processing_failures TO netpulse_airflow;
GRANT SELECT ON public.network_incidents TO netpulse_airflow;

GRANT SELECT, INSERT, UPDATE, DELETE ON public.dim_agent TO netpulse_airflow;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.dim_endpoint TO netpulse_airflow;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.dim_date TO netpulse_airflow;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.dim_probe TO netpulse_airflow;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.fact_reliability_daily TO netpulse_airflow;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.fact_incident TO netpulse_airflow;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.bridge_incident_agent TO netpulse_airflow;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.bridge_incident_endpoint TO netpulse_airflow;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.analytics_job_runs TO netpulse_airflow;
GRANT SELECT, INSERT, UPDATE ON public.analytics_orchestration_runs TO netpulse_airflow;
GRANT SELECT ON public.v_daily_probe_reliability TO netpulse_airflow;
GRANT SELECT ON public.v_incident_summary TO netpulse_airflow;
GRANT USAGE, SELECT ON SEQUENCE public.analytics_job_runs_run_id_seq TO netpulse_airflow;
SQL
