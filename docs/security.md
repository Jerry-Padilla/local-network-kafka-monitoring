# Security and privacy

Phase 1 is designed for loopback-only local development.

- No active secrets are committed. `.env.example` contains visibly nonproduction
  placeholders; `.env` is ignored.
- PostgreSQL migrations use the administrator role, while ingestion uses the
  limited `netpulse_app` role.
- Kafka and PostgreSQL bind only to loopback and are not suitable for public
  exposure in their current plaintext configuration.
- Images run application code as a non-root UID. Infrastructure images retain
  their upstream defaults.
- Event and configuration validation rejects unsupported types, agents, and
  endpoints. The simulator does not scan networks.
- Logs contain source coordinates and error classes but must not contain
  credentials. Original invalid payloads are retained in PostgreSQL and the
  dead-letter topic, so real deployments must restrict access and retention.
- Sample SSIDs, BSSIDs, hostnames, endpoints, and network identifiers are
  fabricated. Later agent configuration will allow redaction or hashing.

Before shared or remote deployment, add encrypted Kafka transport and
authentication, rotate all credentials, restrict container networks and host
firewalls, and run dependency/container scanning. Example checks:

```text
pip-audit -r requirements-dev.txt
docker scout cves netpulse-event-ingestor
docker scout cves netpulse-simulator
```

These commands are instructions, not claims that scans have run.
