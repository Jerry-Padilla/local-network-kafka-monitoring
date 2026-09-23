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
