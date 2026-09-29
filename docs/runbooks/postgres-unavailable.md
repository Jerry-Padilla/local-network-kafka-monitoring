# PostgreSQL unavailable
## Symptoms
`NetPulsePostgresUnavailable` reports `pg_up == 0` while the exporter itself is reachable.
## Safety
Preserve the database volume. Never initialize or replace it as a recovery shortcut.
## Diagnosis
Run `docker compose ps postgres postgres-exporter`, inspect their logs, and verify monitoring credentials were provisioned.
## Remediation
Start PostgreSQL, correct credentials or disk pressure, then restart only the exporter if its connection remains stale.
## Recovery verification
Confirm `pg_up` is 1 and a read-only query against `v_sre_pipeline_status` succeeds.
## Escalation
Escalate on corruption, repeated crash recovery, or an unexpectedly full disk.
