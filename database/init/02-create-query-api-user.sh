#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${QUERY_API_POSTGRES_PASSWORD:-}" ]]; then
  echo "QUERY_API_POSTGRES_PASSWORD must be set" >&2
  exit 1
fi

psql_args=(
  --set ON_ERROR_STOP=1
  --username "$POSTGRES_USER"
  --dbname "$POSTGRES_DB"
  --set query_api_password="$QUERY_API_POSTGRES_PASSWORD"
)
if [[ -n "${PGHOST:-}" ]]; then
  psql_args+=(--host "$PGHOST")
fi

psql "${psql_args[@]}" <<'SQL'
SELECT format(
  'CREATE ROLE netpulse_query_api LOGIN PASSWORD %L',
  :'query_api_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_query_api')
\gexec

SELECT format('ALTER ROLE netpulse_query_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS INHERIT PASSWORD %L', :'query_api_password')
\gexec

SELECT format('REVOKE %I FROM netpulse_query_api', parent.rolname)
FROM pg_auth_members AS membership
JOIN pg_roles AS parent ON parent.oid = membership.roleid
JOIN pg_roles AS member ON member.oid = membership.member
WHERE member.rolname = 'netpulse_query_api'
  AND parent.rolname <> 'netpulse_report'
\gexec

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'netpulse_report') THEN
    GRANT netpulse_report TO netpulse_query_api;
  END IF;
END $$;
SQL
