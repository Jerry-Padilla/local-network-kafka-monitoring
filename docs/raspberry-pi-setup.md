# Raspberry Pi agent setup

## Supported role

The current hardware target is the Raspberry Pi 3 Model B+ running 64-bit
Raspberry Pi OS Lite Trixie. Pi Zero models are outside the current project
scope. The Phase 2 agent is intentionally lightweight: Python collectors,
SQLite, and a Kafka producer only. Do not install Kafka, PostgreSQL, Spark,
Docker, or Kubernetes on the Pi. Trixie uses Python 3.13 by default. The agent
and contracts packages permit Python 3.12 and 3.13, but installation and
resource use on the physical Pi 3 B+ are not yet validated. The Python 3.13
CI job runs on x86_64 Linux; it does not establish ARM64 hardware compatibility.

For a wired Pi 3 B+, start from `config/agent-ethernet.example.yaml`; for a
Wi-Fi Pi 3 B+, start from `config/agent.example.yaml`. These are alternatives
for one device, not evidence that two physical agents are deployed. All
addresses in those files are documentation ranges and must be replaced with
endpoints you own or are authorized to monitor.

## Operating-system prerequisites

Install Raspberry Pi OS Lite and enable time synchronization. Event timestamps
must be UTC. Install the minimum operating-system packages:

```bash
sudo apt update
sudo apt install --no-install-recommends python3 python3-venv \
  iputils-ping iw
```

The optional speed-test collector additionally requires `speedtest-cli`; leave
it disabled unless installed and deliberately scheduled.

## Application installation

From a trusted checkout of this repository:

```bash
sudo useradd --system --home-dir /var/lib/netpulse-agent \
  --create-home --shell /usr/sbin/nologin netpulse
sudo mkdir -p /opt/netpulse-agent /etc/netpulse-agent
sudo python3 -m venv /opt/netpulse-agent/venv
sudo /opt/netpulse-agent/venv/bin/pip install \
  ./packages/contracts ./services/network-agent
sudo cp config/agent.example.yaml /etc/netpulse-agent/agent.yaml
sudo cp deployment/systemd/agent.env.example /etc/netpulse-agent/agent.env
sudo cp deployment/systemd/netpulse-agent.service \
  /etc/systemd/system/netpulse-agent.service
sudo chown -R root:root /opt/netpulse-agent /etc/netpulse-agent
sudo chown root:netpulse /etc/netpulse-agent/agent.yaml
sudo chmod 0640 /etc/netpulse-agent/agent.yaml \
  /etc/netpulse-agent/agent.env
```

Edit `/etc/netpulse-agent/agent.yaml`:

- use the device's stable `agent_id` and correct role;
- replace every documentation-only endpoint;
- keep each `endpoint_id` aligned with a row in the backend `endpoints` table;
- confirm the Wi-Fi interface name with `iw dev`;
- use endpoint aliases and keep `include_target_addresses: false` unless raw
  addresses are explicitly required;
- replace the hash salt even when SSID/BSSID storage is currently disabled;
- keep speed tests disabled until their bandwidth and schedule are acceptable;
- point Kafka at the backend computer's private LAN address, not
  `localhost:29092`.

The Kafka listener must be deliberately configured for private-LAN access and
protected by the host firewall. Phase 1's default listener is loopback-only, so
it cannot accept Pi connections without an explicit deployment change.

## Read-only Pi preflight

Before enabling the service, run the repository's noninteractive preflight on
the target Pi. It only reads local platform metadata and validates the agent
configuration: it does not install packages, start services, alter firewall
rules, or make network connections.

```bash
cd /path/to/trusted/netpulse-checkout
sudo -u netpulse env NETPULSE_PI_PREFLIGHT_AGENT_BIN=/opt/netpulse-agent/venv/bin/netpulse-agent \
  bash ./deployment/pi/netpulse-pi-preflight.sh
```

It requires an observed Raspberry Pi 3 Model B+, a 64-bit userspace, Trixie
Debian/Raspberry Pi OS metadata, Python 3.12 or 3.13, `systemd`, `ping`, `iw`,
and a configuration that passes `validate-config`. A nonzero exit status means
do not enable the service until the failing item is resolved. The script's
success message is evidence only for the specific host on which it ran; it is
not a substitute for service, Wi-Fi, Kafka, or recovery acceptance.

This YAML check deliberately runs as `netpulse`, confirming that the same
service identity can read `/etc/netpulse-agent/agent.yaml`. It does not apply
the root-readable systemd `agent.env` overrides. Run this second, read-only
effective-configuration check before enabling the service:

```bash
sudo env NETPULSE_PI_PREFLIGHT_AGENT_BIN=/opt/netpulse-agent/venv/bin/netpulse-agent \
  bash ./deployment/pi/netpulse-pi-preflight.sh \
  --effective-env-file /etc/netpulse-agent/agent.env
```

The effective check requires root only to read and verify the root-owned,
non-group/world-writable `agent.env`; it then runs `validate-config` as
`netpulse` with those overrides. Keep `agent.env` to comments and unquoted
`KEY=VALUE` assignments, as in `deployment/systemd/agent.env.example`; quoted
or escaped values are rejected so the preflight cannot misrepresent systemd's
environment parsing. This validates configuration only: it does not prove that
systemd's sandbox applies or that the service can execute `ping` at runtime.
Inspect the enabled service and its journal after offline acceptance.

For a pre-install platform check, omit the installed-agent validation:

```bash
bash ./deployment/pi/netpulse-pi-preflight.sh --skip-agent-check
```

The repository has not observed this command on a physical Pi in the current
development environment. Record the exact command and output from the target
device with the deployment evidence; do not infer Pi compatibility from CI or
from this workstation.

## Offline acceptance before enabling the service

Validate configuration and collect once without Kafka publication:

```bash
sudo -u netpulse /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml validate-config
sudo -u netpulse /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml collect-once
sudo -u netpulse /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml outbox-status
```

The last command must show pending records even when Kafka is unreachable.
After Kafka becomes reachable, run `publish-once` and verify that pending falls
to zero. Delivery is at least once: an acknowledgement lost during a crash can
cause Kafka replay, while `event_id` deduplicates PostgreSQL writes.

## Headless service

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netpulse-agent
sudo systemctl status netpulse-agent
sudo journalctl -u netpulse-agent -f
```

The service runs as `netpulse`, writes only under
`/var/lib/netpulse-agent`, restarts after failure, and waits for
`network-online.target`. A missing `iw` command or unavailable Wi-Fi interface
creates failure telemetry and does not terminate the Ethernet agent.

## Storage and recovery

SQLite uses WAL mode and full synchronization. New events are rejected with a
visible error if `maximum_bytes` would be exceeded; undelivered records are
never silently deleted. Acknowledged records are retained for the configured
period and then pruned. Monitor `local_queue_depth` in heartbeat events and the
`outbox-status` command.

Back up or stop the service before manually copying the SQLite database. Do not
edit the database directly while the service is running.

## Physical Pi deployment on the trusted LAN

The checked-in `config/agent-pi.yaml` is the deployment configuration for the
physical Wi-Fi Pi. It retains the SQLite outbox and privacy defaults, uses the
already registered `network-agent-wifi-01` identity, sends Kafka records to
`192.168.1.198:29092`, pings the router at `192.168.1.254`, and uses `1.1.1.1`
for the external reachability measurement. DNS, HTTP, and speed tests remain
disabled so the deployment contains no documentation-only or unauthorized
targets. Wi-Fi diagnostics are enabled after the literal interface reported by
`iw dev` is installed in the configuration.

Copy a trusted checkout to the Pi at `$HOME/netpulse`, then run:

```bash
set -eu
cd "$HOME/netpulse"

sudo apt update
sudo apt install --no-install-recommends \
  python3 python3-venv iputils-ping iw netcat-openbsd openssl

bash ./deployment/pi/netpulse-pi-preflight.sh --skip-agent-check

id -u netpulse >/dev/null 2>&1 || \
  sudo useradd --system --home-dir /var/lib/netpulse-agent \
    --create-home --shell /usr/sbin/nologin netpulse
sudo install -d -o root -g root -m 0755 /opt/netpulse-agent /etc/netpulse-agent
sudo install -d -o netpulse -g netpulse -m 0750 /var/lib/netpulse-agent
sudo python3 -m venv /opt/netpulse-agent/venv
sudo /opt/netpulse-agent/venv/bin/pip install --upgrade pip
sudo /opt/netpulse-agent/venv/bin/pip install \
  ./packages/contracts ./services/network-agent

WIFI_INTERFACE="$(iw dev | awk '$1 == "Interface" {print $2; exit}')"
test -n "$WIFI_INTERFACE" || {
  echo "No Wi-Fi interface was reported by iw dev" >&2
  exit 1
}
echo "Using Wi-Fi interface: $WIFI_INTERFACE"
PRIVATE_SALT="$(openssl rand -hex 32)"

sudo install -o root -g netpulse -m 0640 \
  config/agent-pi.yaml /etc/netpulse-agent/agent.yaml
sudo sed -i \
  -e "s/interface: wlan0/interface: $WIFI_INTERFACE/" \
  -e "s/replace-this-with-a-private-device-specific-salt/$PRIVATE_SALT/" \
  /etc/netpulse-agent/agent.yaml
unset PRIVATE_SALT

sudo install -o root -g root -m 0640 \
  deployment/systemd/agent.env.example /etc/netpulse-agent/agent.env
sudo install -o root -g root -m 0644 \
  deployment/systemd/netpulse-agent.service \
  /etc/systemd/system/netpulse-agent.service

sudo env \
  NETPULSE_PI_PREFLIGHT_AGENT_BIN=/opt/netpulse-agent/venv/bin/netpulse-agent \
  bash ./deployment/pi/netpulse-pi-preflight.sh \
  --effective-env-file /etc/netpulse-agent/agent.env
sudo -u netpulse /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml validate-config

nc -vz -w 5 192.168.1.198 29092

sudo -u netpulse /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml collect-once
sudo -u netpulse /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml outbox-status
sudo -u netpulse /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml publish-once
sudo -u netpulse /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml outbox-status
```

The first status must show `pending` greater than zero after `collect-once`.
After Kafka acknowledges the batch, the second status must show `pending: 0`.
If an earlier failed attempt placed records in retry backoff, wait and repeat
`publish-once`; a single call publishes at most one eligible batch. Do not run
`publish-once` concurrently with the systemd service.

After the first event is visible in PostgreSQL, start continuous collection:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now netpulse-agent
sudo systemctl is-enabled netpulse-agent
sudo systemctl is-active netpulse-agent
sudo systemctl status netpulse-agent --no-pager
sudo journalctl -u netpulse-agent -n 100 --no-pager
sudo journalctl -u netpulse-agent -f
```

If `confluent-kafka` has no ARM64 wheel for the installed Python version, add
`build-essential python3-dev librdkafka-dev` and retry only the two local pip
installs. Do not install Kafka, PostgreSQL, Spark, or Docker on the Pi.

## Backend Kafka LAN listener and firewall

The Compose defaults remain loopback-only for safe local development. The
backend `.env` used for this physical deployment must contain:

```dotenv
KAFKA_EXTERNAL_PORT=29092
KAFKA_LAN_HOST=192.168.1.198
KAFKA_EXTERNAL_BIND_ADDRESS=0.0.0.0
```

Validate and start only the existing backend services from the repository:

```powershell
docker compose config --quiet
pwsh -NoProfile -File scripts/verify_kafka_lan_config.ps1
docker compose up -d --build --wait event-ingestor
docker compose ps -a
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh `
  --bootstrap-server kafka:9092 --list
docker compose exec -T kafka /opt/kafka/bin/kafka-consumer-groups.sh `
  --bootstrap-server kafka:9092 --describe --group netpulse-ingestion-v1
Test-NetConnection 192.168.1.198 -Port 29092
```

In an elevated PowerShell window, allow only the private LAN to reach Kafka.
This is a host firewall rule, not router port forwarding:

```powershell
New-NetFirewallRule `
  -DisplayName 'NetPulse Kafka from private LAN' `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 29092 `
  -Profile Private -RemoteAddress 192.168.1.0/24
Get-NetFirewallRule -DisplayName 'NetPulse Kafka from private LAN' |
  Get-NetFirewallPortFilter
Get-NetFirewallRule -DisplayName 'NetPulse Kafka from private LAN' |
  Get-NetFirewallAddressFilter
```

PostgreSQL remains published on `127.0.0.1`; no other service gains a LAN
binding. If the Pi's fixed IP is known, replace `192.168.1.0/24` with that one
address for a tighter firewall scope.

## Verify physical-Pi ingestion

Use the container-internal `kafka:9092` listener for backend inspection:

```powershell
docker compose exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh `
  --bootstrap-server kafka:9092 --topic network.agent-heartbeats.v1 `
  --from-beginning --timeout-ms 10000 --property print.timestamp=true `
  --property print.key=true
docker compose exec -T kafka /opt/kafka/bin/kafka-console-consumer.sh `
  --bootstrap-server kafka:9092 --topic network.measurements.raw.v1 `
  --from-beginning --timeout-ms 10000 --property print.timestamp=true `
  --property print.key=true
docker compose logs --since 10m event-ingestor |
  Select-String 'partitions_assigned|record_processed|record_processing_failed'
```

The records must use key and `agent_id` `network-agent-wifi-01`. Measurement
records must include `router_ping`, `external_ping`, and `wifi_diagnostics`.
The following PostgreSQL checks prove typed persistence and preservation of the
original collection timestamp:

```powershell
docker compose exec -T postgres psql -U netpulse_admin -d netpulse `
  -P pager=off -c "SELECT r.received_at,r.event_time,r.published_time,r.event_type,r.agent_id,r.source_topic,r.source_partition,r.source_offset,(r.payload->>'event_time')::timestamptz AS payload_event_time,(r.event_time=(r.payload->>'event_time')::timestamptz) AS timestamp_preserved FROM raw_events r WHERE r.agent_id='network-agent-wifi-01' ORDER BY r.received_at DESC LIMIT 30;"

docker compose exec -T postgres psql -U netpulse_admin -d netpulse `
  -P pager=off -c "SELECT h.event_time,h.agent_id,h.hostname,h.agent_version,h.network_interfaces,h.collection_errors,h.local_queue_depth,r.received_at FROM agent_heartbeats h JOIN raw_events r USING(event_id) WHERE h.agent_id='network-agent-wifi-01' ORDER BY h.event_time DESC LIMIT 10;"

docker compose exec -T postgres psql -U netpulse_admin -d netpulse `
  -P pager=off -c "SELECT m.event_time,r.received_at,m.agent_id,m.measurement_type,m.target_id,m.success,m.latency_ms,m.packet_loss_pct,m.signal_dbm,m.connected,(m.event_time=r.event_time) AS typed_time_matches_raw,(r.event_time=(r.payload->>'event_time')::timestamptz) AS original_time_preserved FROM network_measurements m JOIN raw_events r USING(event_id) WHERE m.agent_id='network-agent-wifi-01' ORDER BY m.event_time DESC LIMIT 50;"

docker compose exec -T postgres psql -U netpulse_admin -d netpulse `
  -P pager=off -c "SELECT measurement_type,count(*) AS rows,min(event_time) AS first_event,max(event_time) AS latest_event FROM network_measurements WHERE agent_id='network-agent-wifi-01' GROUP BY measurement_type ORDER BY measurement_type;"

docker compose exec -T postgres psql -U netpulse_admin -d netpulse `
  -P pager=off -c "SELECT failure_id,first_failed_at,source_topic,source_partition,source_offset,source_key,error_class,error_message,dead_letter_published_at FROM processing_failures WHERE source_key='network-agent-wifi-01' ORDER BY first_failed_at DESC;"
```

The final query must return zero rows. Capture the total failure count before
the Pi test if retained simulator history exists, so only newly created rows
are treated as regressions.

## SQLite outage and recovery acceptance

After continuous collection is active, record the Pi's current `pending`
count, stop Kafka on the backend, wait at least 70 seconds, and inspect the Pi
again:

```powershell
docker compose stop kafka
```

```bash
sudo -u netpulse /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml outbox-status
sudo journalctl -u netpulse-agent --since '2 minutes ago' --no-pager
```

`pending` must increase. Restore Kafka and wait for its health check:

```powershell
docker compose start kafka
docker compose up -d --wait topic-init event-ingestor
docker compose ps -a
```

Leave systemd running and poll `outbox-status`; do not run a competing manual
publisher. The service retries with exponential backoff capped at 300 seconds,
so queued rows may not become eligible immediately. Acceptance requires
`pending: 0`, new PostgreSQL rows whose `event_time` predates `received_at`,
and no new Pi-keyed `processing_failures` rows.
