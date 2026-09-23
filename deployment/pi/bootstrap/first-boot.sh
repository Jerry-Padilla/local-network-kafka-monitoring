#!/usr/bin/env bash
set -Eeuo pipefail

BUNDLE=/boot/firmware/netpulse-bootstrap
STATE_DIR=/var/lib/netpulse-bootstrap
LOG_FILE=/var/log/netpulse-bootstrap.log
SUCCESS_MARKER="$STATE_DIR/succeeded"
FAILED_MARKER="$STATE_DIR/failed"

install -d -o root -g root -m 0755 "$STATE_DIR"
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
  "$BUNDLE/packages/contracts" "$BUNDLE/services/network-agent"

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
