#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${GRAFANA_POSTGRES_PASSWORD:-}" ]]; then
  echo "GRAFANA_POSTGRES_PASSWORD must be set" >&2
  exit 1
fi
if [[ -z "${POSTGRES_EXPORTER_PASSWORD:-}" ]]; then
  echo "POSTGRES_EXPORTER_PASSWORD must be set" >&2
  exit 1
fi

psql_args=(
  --set ON_ERROR_STOP=1
  --username "$POSTGRES_USER"
  --dbname "$POSTGRES_DB"
  --set grafana_password="$GRAFANA_POSTGRES_PASSWORD"
  --set exporter_password="$POSTGRES_EXPORTER_PASSWORD"
)
if [[ -n "${PGHOST:-}" ]]; then
  psql_args+=(--host "$PGHOST")
fi

psql "${psql_args[@]}" <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_report') THEN
    CREATE ROLE netpulse_report NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_monitor') THEN
    CREATE ROLE netpulse_monitor NOLOGIN;
  END IF;
END $$;

SELECT format(
  'CREATE ROLE netpulse_grafana LOGIN PASSWORD %L',
  :'grafana_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_grafana')
\gexec
SELECT format('ALTER ROLE netpulse_grafana LOGIN PASSWORD %L', :'grafana_password')
\gexec

SELECT format(
  'CREATE ROLE netpulse_postgres_exporter LOGIN PASSWORD %L',
  :'exporter_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_postgres_exporter')
\gexec
SELECT format(
  'ALTER ROLE netpulse_postgres_exporter LOGIN PASSWORD %L',
  :'exporter_password'
)
\gexec

GRANT pg_monitor TO netpulse_monitor;
GRANT netpulse_report TO netpulse_grafana;
GRANT netpulse_monitor TO netpulse_postgres_exporter;
SQL
