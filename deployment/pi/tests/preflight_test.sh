#!/usr/bin/env bash
# Fixture tests for the read-only Raspberry Pi preflight script.
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
preflight="$repo_root/deployment/pi/netpulse-pi-preflight.sh"
fixture_root=$(mktemp -d)
trap 'rm -rf "$fixture_root"' EXIT

mkdir -p "$fixture_root/proc/device-tree" "$fixture_root/etc" "$fixture_root/bin"
printf 'Raspberry Pi 3 Model B Plus Rev 1.3\0' > "$fixture_root/proc/device-tree/model"
cat > "$fixture_root/etc/os-release" <<'EOF'
ID=debian
VERSION_CODENAME=trixie
EOF

cat > "$fixture_root/bin/getconf" <<'EOF'
#!/usr/bin/env bash
test "$1" = LONG_BIT
printf '64\n'
EOF
cat > "$fixture_root/bin/python3" <<'EOF'
#!/usr/bin/env bash
test "$1" = -c
printf '3.13\n'
EOF
cat > "$fixture_root/bin/systemctl" <<'EOF'
#!/usr/bin/env bash
test "$1" = --version
printf 'systemd 257\n'
EOF
cat > "$fixture_root/bin/ping" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
cat > "$fixture_root/bin/iw" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$fixture_root/bin"/*

PATH="$fixture_root/bin:$PATH" "$preflight" --root "$fixture_root" --skip-agent-check

printf 'agent: {}\n' > "$fixture_root/agent.yaml"
cat > "$fixture_root/bin/fixture-netpulse-agent" <<'EOF'
#!/usr/bin/env bash
test "$1" = --config
test "$3" = validate-config
test "$(cat "$2")" != invalid
if [[ -n "${FIXTURE_RUNUSER_USER:-}" ]]; then
  test "$FIXTURE_RUNUSER_USER" = netpulse
  test "${NETPULSE_AGENT_ROLE:-}" = wifi_observer
fi
EOF
cat > "$fixture_root/bin/runuser" <<'EOF'
#!/usr/bin/env bash
test "$1" = -u
test "$2" = netpulse
test "$3" = --
export FIXTURE_RUNUSER_USER="$2"
shift 3
exec "$@"
EOF
cat > "$fixture_root/bin/id" <<'EOF'
#!/usr/bin/env bash
test "$1" = -u
printf '%s\n' "${FIXTURE_UID:-0}"
EOF
cat > "$fixture_root/bin/stat" <<'EOF'
#!/usr/bin/env bash
test "$1" = -c
case "$2" in
  %u) printf '%s\n' "${FIXTURE_STAT_OWNER:-0}" ;;
  %a) printf '%s\n' "${FIXTURE_STAT_MODE:-640}" ;;
  *) exit 2 ;;
esac
EOF
chmod +x "$fixture_root/bin/fixture-netpulse-agent"
chmod +x "$fixture_root/bin/runuser"
chmod +x "$fixture_root/bin/id" "$fixture_root/bin/stat"
PATH="$fixture_root/bin:$PATH" \
  NETPULSE_PI_PREFLIGHT_AGENT_BIN=fixture-netpulse-agent \
  NETPULSE_PI_PREFLIGHT_CONFIG="$fixture_root/agent.yaml" \
  "$preflight" --root "$fixture_root"

printf 'NETPULSE_AGENT_ROLE=wifi_observer\n' > "$fixture_root/agent.env"
output=$(PATH="$fixture_root/bin:$PATH" \
  NETPULSE_PI_PREFLIGHT_AGENT_BIN=fixture-netpulse-agent \
  NETPULSE_PI_PREFLIGHT_CONFIG="$fixture_root/agent.yaml" \
  "$preflight" --root "$fixture_root" --effective-env-file "$fixture_root/agent.env" 2>&1)
if [[ "$output" != *"effective agent configuration validates"* ]]; then
  echo "expected valid effective environment configuration, got: $output" >&2
  exit 1
fi

if output=$(PATH="$fixture_root/bin:$PATH" \
  FIXTURE_UID=1000 \
  NETPULSE_PI_PREFLIGHT_AGENT_BIN=fixture-netpulse-agent \
  NETPULSE_PI_PREFLIGHT_CONFIG="$fixture_root/agent.yaml" \
  "$preflight" --root "$fixture_root" --effective-env-file "$fixture_root/agent.env" 2>&1); then
  echo "expected non-root effective environment validation to fail preflight" >&2
  exit 1
elif [[ "$output" != *"effective environment validation requires root"* ]]; then
  echo "expected root requirement failure, got: $output" >&2
  exit 1
fi

if output=$(PATH="$fixture_root/bin:$PATH" \
  FIXTURE_STAT_OWNER=1000 \
  NETPULSE_PI_PREFLIGHT_AGENT_BIN=fixture-netpulse-agent \
  NETPULSE_PI_PREFLIGHT_CONFIG="$fixture_root/agent.yaml" \
  "$preflight" --root "$fixture_root" --effective-env-file "$fixture_root/agent.env" 2>&1); then
  echo "expected non-root-owned environment file to fail preflight" >&2
  exit 1
elif [[ "$output" != *"effective environment file must be root-owned"* ]]; then
  echo "expected owner failure, got: $output" >&2
  exit 1
fi

if output=$(PATH="$fixture_root/bin:$PATH" \
  FIXTURE_STAT_MODE=660 \
  NETPULSE_PI_PREFLIGHT_AGENT_BIN=fixture-netpulse-agent \
  NETPULSE_PI_PREFLIGHT_CONFIG="$fixture_root/agent.yaml" \
  "$preflight" --root "$fixture_root" --effective-env-file "$fixture_root/agent.env" 2>&1); then
  echo "expected group-writable environment file to fail preflight" >&2
  exit 1
elif [[ "$output" != *"effective environment file must be root-owned"* ]]; then
  echo "expected mode failure, got: $output" >&2
  exit 1
fi

printf 'NETPULSE_AGENT_ROLE=not-a-valid-role\n' > "$fixture_root/agent.env"
if output=$(PATH="$fixture_root/bin:$PATH" \
  NETPULSE_PI_PREFLIGHT_AGENT_BIN=fixture-netpulse-agent \
  NETPULSE_PI_PREFLIGHT_CONFIG="$fixture_root/agent.yaml" \
  "$preflight" --root "$fixture_root" --effective-env-file "$fixture_root/agent.env" 2>&1); then
  echo "expected invalid environment override to fail preflight" >&2
  exit 1
elif [[ "$output" != *"effective agent configuration does not validate"* ]]; then
  echo "expected effective configuration validation failure, got: $output" >&2
  exit 1
fi

# This harness runs as an unprivileged Git Bash user (not uid 0). A mode-000
# configuration must not be accepted merely because the agent command exists.
chmod 000 "$fixture_root/agent.yaml"
if [[ -r "$fixture_root/agent.yaml" ]]; then
  echo "SKIP unreadable-config assertion: host does not enforce POSIX mode bits"
else
  if PATH="$fixture_root/bin:$PATH" \
    NETPULSE_PI_PREFLIGHT_AGENT_BIN=fixture-netpulse-agent \
    NETPULSE_PI_PREFLIGHT_CONFIG="$fixture_root/agent.yaml" \
    "$preflight" --root "$fixture_root"; then
    echo "expected unreadable agent configuration to fail preflight" >&2
    exit 1
  fi
fi
chmod 600 "$fixture_root/agent.yaml"

cat > "$fixture_root/etc/os-release" <<'EOF'
ID=debian
VERSION_CODENAME=bookworm
EOF
if output=$(PATH="$fixture_root/bin:$PATH" "$preflight" --root "$fixture_root" --skip-agent-check 2>&1); then
  echo "expected unsupported OS metadata to fail preflight" >&2
  exit 1
elif [[ "$output" != *"requires Raspberry Pi OS Lite Trixie-compatible metadata"* ]]; then
  echo "expected OS metadata failure, got: $output" >&2
  exit 1
fi
cat > "$fixture_root/etc/os-release" <<'EOF'
ID=debian
VERSION_CODENAME=trixie
EOF

cat > "$fixture_root/bin/python3" <<'EOF'
#!/usr/bin/env bash
test "$1" = -c
printf '3.11\n'
EOF
chmod +x "$fixture_root/bin/python3"
if output=$(PATH="$fixture_root/bin:$PATH" "$preflight" --root "$fixture_root" --skip-agent-check 2>&1); then
  echo "expected unsupported Python version to fail preflight" >&2
  exit 1
elif [[ "$output" != *"requires Python 3.12 or 3.13"* ]]; then
  echo "expected Python version failure, got: $output" >&2
  exit 1
fi
cat > "$fixture_root/bin/python3" <<'EOF'
#!/usr/bin/env bash
test "$1" = -c
printf '3.13\n'
EOF
chmod +x "$fixture_root/bin/python3"

rm "$fixture_root/bin/iw"
if output=$(PATH="$fixture_root/bin:$PATH" "$preflight" --root "$fixture_root" --skip-agent-check 2>&1); then
  echo "expected missing iw command to fail preflight" >&2
  exit 1
elif [[ "$output" != *"command iw is unavailable"* ]]; then
  echo "expected missing-command failure, got: $output" >&2
  exit 1
fi

printf 'Raspberry Pi 4 Model B Rev 1.5\0' > "$fixture_root/proc/device-tree/model"
if PATH="$fixture_root/bin:$PATH" "$preflight" --root "$fixture_root" --skip-agent-check; then
  echo "expected preflight to reject a non-Pi-3-B+ model" >&2
  exit 1
fi
