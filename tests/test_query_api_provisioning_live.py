"""Host-side PostgreSQL 17 role-grant regression for query API provisioning."""

from __future__ import annotations

import subprocess
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.host_integration]
ROOT = Path(__file__).resolve().parents[1]
_PSQL = (
    "exec",
    "-T",
    "postgres",
    "sh",
    "-c",
    'psql -X -q -At -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"',
)


def _compose(*args: str, sql: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", *args],
        cwd=ROOT,
        input=sql,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def _sql(statement: str) -> str:
    result = _compose(*_PSQL, sql=statement)
    if result.returncode != 0:
        pytest.fail("query API role regression SQL failed", pytrace=False)
    return result.stdout.strip()


def test_provisioner_removes_delegated_grantor_membership() -> None:
    suffix = uuid4().hex
    broad_role = f"query_api_scope_{suffix}"
    grantor_role = f"query_api_grantor_{suffix}"
    _sql(
        f'BEGIN; CREATE ROLE "{broad_role}" NOLOGIN; '
        f'CREATE ROLE "{grantor_role}" NOLOGIN; '
        f'GRANT SELECT ON public.v_incident_summary TO "{broad_role}"; '
        f'GRANT "{broad_role}" TO "{grantor_role}" WITH ADMIN OPTION; '
        f'GRANT "{broad_role}" TO netpulse_query_api GRANTED BY "{grantor_role}"; '
        "COMMIT;"
    )
    try:
        grantor = _sql(
            "SELECT grantor.rolname FROM pg_auth_members AS membership "
            "JOIN pg_roles AS parent ON parent.oid = membership.roleid "
            "JOIN pg_roles AS member ON member.oid = membership.member "
            "JOIN pg_roles AS grantor ON grantor.oid = membership.grantor "
            f"WHERE parent.rolname = '{broad_role}' "
            "AND member.rolname = 'netpulse_query_api';"
        )
        assert grantor == grantor_role
        assert (
            _sql(
                "SELECT has_table_privilege('netpulse_query_api', 'v_incident_summary', 'SELECT');"
            )
            == "t"
        )

        provision = _compose("--profile", "api", "run", "--rm", "--no-deps", "query-api-init")
        assert provision.returncode == 0, "query API provisioning failed"
        privileges = _sql(
            "SELECT (SELECT count(*) FROM pg_auth_members AS membership "
            "JOIN pg_roles AS member ON member.oid = membership.member "
            "WHERE member.rolname = 'netpulse_query_api'), "
            "has_table_privilege('netpulse_query_api', "
            "'v_daily_probe_reliability', 'SELECT'), "
            "has_table_privilege('netpulse_query_api', "
            "'v_incident_summary', 'SELECT'), "
            "has_table_privilege('netpulse_query_api', "
            "'v_grafana_live_measurements', 'SELECT');"
        )
        assert privileges == "0|t|f|f"
    finally:
        _sql(
            f'BEGIN; REVOKE "{broad_role}" FROM "{grantor_role}" CASCADE; '
            f'REVOKE SELECT ON public.v_incident_summary FROM "{broad_role}"; '
            f'DROP ROLE "{grantor_role}"; DROP ROLE "{broad_role}"; COMMIT;'
        )
