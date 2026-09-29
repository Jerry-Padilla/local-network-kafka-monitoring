#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_PREFIX=${NETPULSE_BOOTSTRAP_ROOT:-}
BUNDLE=${NETPULSE_BOOTSTRAP_BUNDLE:-${ROOT_PREFIX}/boot/firmware/netpulse-bootstrap}
STATE_DIR="${ROOT_PREFIX}/var/lib/netpulse-bootstrap"
LOG_FILE="${ROOT_PREFIX}/var/log/netpulse-bootstrap.log"
SUCCESS_MARKER="$STATE_DIR/succeeded"
FAILED_MARKER="$STATE_DIR/failed"

install -d -m 0755 "$STATE_DIR" "$(dirname "$LOG_FILE")"
if [[ -z "$ROOT_PREFIX" ]]; then
  chown root:root "$STATE_DIR" "$(dirname "$LOG_FILE")"
fi
touch "$LOG_FILE"
chmod 0644 "$LOG_FILE"
exec > >(tee -a "$LOG_FILE") 2>&1

on_error() {
  status=$?
  printf 'NetPulse bootstrap failed at line %s (exit %s)\n' "$1" "$status"
  printf '%s\n' "$(date -u +%FT%TZ)" > "$FAILED_MARKER"
  exit "$status"
}
trap 'on_error $LINENO' ERR

if [[ -f "$SUCCESS_MARKER" ]]; then
  echo 'NetPulse bootstrap already completed.'
  exit 0
fi

if [[ ! -f "$BUNDLE/agent.env" ]]; then
  echo "Missing $BUNDLE/agent.env; copy agent.env.example to agent.env before first boot." >&2
  exit 2
fi

apt-get update
apt-get install -y --no-install-recommends \
  python3 python3-venv iputils-ping netcat-openbsd openssl

if ! id netpulse >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/netpulse-agent \
    --create-home --shell /usr/sbin/nologin netpulse
fi

install -d -o root -g root -m 0755 /opt/netpulse-agent /etc/netpulse-agent
install -d -o netpulse -g netpulse -m 0750 /var/lib/netpulse-agent
python3 -m venv /opt/netpulse-agent/venv
/opt/netpulse-agent/venv/bin/pip install --upgrade pip
/opt/netpulse-agent/venv/bin/pip install \
  "$BUNDLE/packages/contracts" "$BUNDLE/packages/observability" \
  "$BUNDLE/services/network-agent"

hash_salt="$(openssl rand -hex 32)"

install -o root -g netpulse -m 0640 "$BUNDLE/agent.yaml" \
  /etc/netpulse-agent/agent.yaml
sed -i \
  -e "s/replace-this-with-a-private-device-specific-salt/${hash_salt}/" \
  /etc/netpulse-agent/agent.yaml
unset hash_salt

install -o root -g root -m 0640 "$BUNDLE/agent.env" \
  /etc/netpulse-agent/agent.env
install -o root -g root -m 0644 "$BUNDLE/netpulse-agent.service" \
  /etc/systemd/system/netpulse-agent.service

runuser -u netpulse -- /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml validate-config
runuser -u netpulse -- /opt/netpulse-agent/venv/bin/netpulse-agent \
  --config /etc/netpulse-agent/agent.yaml collect-once

systemctl daemon-reload
rm -f "$FAILED_MARKER"
printf '%s\n' "$(date -u +%FT%TZ)" > "$SUCCESS_MARKER"
echo 'NetPulse bootstrap completed for the wired Ethernet collector.'
echo 'The service is installed but remains disabled until backend ingestion is verified.'
