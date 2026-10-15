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
- The Spark driver also runs as non-root. Its checkpoint and Ivy volumes contain
  query state and downloaded pinned dependencies, not application credentials.
- The classifier runs as non-root and reads only validated operational tables.
  Its recommended actions are fixed rule text, not executable commands.
- Event and configuration validation rejects unsupported types, agents, and
  endpoints. The simulator does not scan networks.
- Logs contain source coordinates and error classes but must not contain
  credentials. Original invalid payloads are retained in PostgreSQL and the
  dead-letter topic, so real deployments must restrict access and retention.
- Sample SSIDs, BSSIDs, hostnames, endpoints, and network identifiers are
  fabricated.
- The network agent monitors only endpoints in its validated YAML file and
  passes command arguments without shell interpolation.
- SSID and BSSID fields default to omission and may be independently hashed
  with a device-local salt. Raw target addresses are omitted from events by
  default.
- GitHub CodeQL analyzes the Python source on pushes and pull requests to
  `master`, on a weekly schedule, and when manually dispatched. The workflow
  uses the `security-extended` query suite with read-only repository access and
  permission to publish code-scanning results.
- Dependabot checks the root and nested Python manifests plus GitHub Actions
  dependencies weekly. Minor and patch updates are grouped; major updates stay
  separate for explicit review.
- GitHub protects `master` with required current pull requests, all ten CI job
  contexts, the CodeQL analysis job, resolved review conversations, linear
  history, and administrator enforcement. Force pushes and branch deletion are
  disabled. Zero approving reviews are required so the solo-maintained project
  is not deadlocked, but all automated gates remain mandatory.

Before shared or remote deployment, add encrypted Kafka transport and
authentication, rotate all credentials, restrict container networks and host
firewalls, and run dependency and container scanning. Example checks:

```text
pip-audit -r requirements-dev.txt
docker scout cves netpulse-event-ingestor
docker scout cves netpulse-simulator
docker scout cves netpulse-stream-processor
docker scout cves netpulse-incident-classifier
```

These commands are instructions, not claims that dependency or container scans
have run. Dependabot version-update checks and CodeQL analysis do not replace
dependency, container-image, or runtime vulnerability scanning.
