# Raspberry Pi agent setup

## Supported role

The Phase 2 agent is intentionally lightweight: Python collectors, SQLite, and
a Kafka producer only. Do not install Kafka, PostgreSQL, Spark, Docker, or
Kubernetes on the Pi Zero W. The checked-in implementation is tested with
Python 3.12; physical Pi Zero W and Pi 3 validation is still required before
claiming measured hardware compatibility.

The wired Pi uses `config/agent-ethernet.example.yaml`. The Wi-Fi Pi uses
`config/agent.example.yaml`. All addresses in those files are documentation
ranges and must be replaced with endpoints you own or are authorized to
monitor.

## Operating-system prerequisites

Install Raspberry Pi OS Lite and enable time synchronization. Event timestamps
must be UTC. Install the minimum operating-system packages:

```bash
sudo apt update
sudo apt install --no-install-recommends python3.12 python3.12-venv \
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
sudo python3.12 -m venv /opt/netpulse-agent/venv
sudo /opt/netpulse-agent/venv/bin/pip install \
  ./packages/contracts ./services/network-agent
sudo cp config/agent.example.yaml /etc/netpulse-agent/agent.yaml
sudo cp deployment/systemd/agent.env.example /etc/netpulse-agent/agent.env
sudo cp deployment/systemd/netpulse-agent.service \
  /etc/systemd/system/netpulse-agent.service
sudo chown -R root:root /opt/netpulse-agent /etc/netpulse-agent
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
