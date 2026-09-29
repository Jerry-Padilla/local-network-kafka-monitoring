#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)
bootstrap="$repo_root/deployment/pi/bootstrap/first-boot.sh"
fixture_root=$(mktemp -d)
trap 'rm -rf "$fixture_root"' EXIT
bundle="$fixture_root/bundle"
mkdir -p "$bundle"

if NETPULSE_BOOTSTRAP_ROOT="$fixture_root/root" \
  NETPULSE_BOOTSTRAP_BUNDLE="$bundle" \
  "$bootstrap" >/dev/null 2>&1; then
  echo "expected an unstaged agent.env to fail first boot" >&2
  exit 1
fi

state_dir="$fixture_root/root/var/lib/netpulse-bootstrap"
installed_env="$fixture_root/root/etc/netpulse-agent/agent.env"
mkdir -p "$state_dir" "$(dirname "$installed_env")"
printf 'already-complete\n' > "$state_dir/succeeded"
printf 'preserve-me\n' > "$installed_env"

NETPULSE_BOOTSTRAP_ROOT="$fixture_root/root" \
  NETPULSE_BOOTSTRAP_BUNDLE="$bundle" \
  "$bootstrap" >/dev/null

test "$(cat "$installed_env")" = preserve-me
echo "first-boot staged-environment and idempotence checks passed"
