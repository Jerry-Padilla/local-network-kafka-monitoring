# Required target down
## Symptoms
`NetPulseTargetDown` identifies a required scrape target with `up == 0`.
## Safety
Inspect before restarting. Preserve PostgreSQL, Kafka, and named volumes.
## Diagnosis
Run `docker compose ps` and inspect the named service with `docker compose logs --tail 200 <service>`. Check `http://localhost:9090/targets`.
## Remediation
Correct its configuration or dependency, then run `docker compose up -d <service>`.
## Recovery verification
Confirm the target is `UP` for two evaluations and the alert resolves.
## Escalation
Escalate if the service repeatedly exits or recovery risks stored data.
