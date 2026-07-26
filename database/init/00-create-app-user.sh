#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${POSTGRES_APP_PASSWORD:-}" ]]; then
  echo "POSTGRES_APP_PASSWORD must be set" >&2
  exit 1
fi

psql --set ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set db_name="$POSTGRES_DB" \
  --set app_password="$POSTGRES_APP_PASSWORD" <<'SQL'
SELECT format(
  'CREATE ROLE netpulse_app LOGIN PASSWORD %L',
  :'app_password'
)
WHERE NOT EXISTS (
  SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = 'netpulse_app'
)
\gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO netpulse_app', :'db_name')
\gexec
SQL
