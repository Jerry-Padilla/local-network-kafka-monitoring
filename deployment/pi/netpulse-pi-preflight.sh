#!/usr/bin/env bash
# Read-only preflight for a NetPulse Raspberry Pi 3 Model B+ installation.
set -euo pipefail

root=/
skip_agent_check=false
effective_env_file=

usage() {
  cat <<'EOF'
Usage: netpulse-pi-preflight.sh [--root PATH] [--skip-agent-check]
                                [--effective-env-file PATH]

Checks the local machine only. It does not install packages, alter services,
open network connections, or read telemetry. --root is intended for fixture
tests; omit it on the Pi. --effective-env-file must be run as root on a Pi;
it checks the supplied systemd EnvironmentFile and validates the resulting
agent configuration as the netpulse service user.
EOF
}

while (($#)); do
  case "$1" in
    --root)
      root=${2:?--root requires a path}
      shift 2
      ;;
    --skip-agent-check)
      skip_agent_check=true
      shift
      ;;
    --effective-env-file)
      effective_env_file=${2:?--effective-env-file requires a path}
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "error: unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

root=${root%/}
[[ -n "$root" ]] || root=/
failures=0

pass() { printf 'PASS %s\n' "$1"; }
fail() {
  printf 'FAIL %s\n' "$1" >&2
  failures=$((failures + 1))
}
root_file() { printf '%s/%s' "$root" "${1#/}"; }
os_value() {
  local key=$1 os_release line
  os_release=$(root_file /etc/os-release)
  [[ -r "$os_release" ]] || return 1
  line=$(grep -E "^${key}=" "$os_release" | head -n 1) || return 1
  printf '%s' "${line#*=}" | tr -d '"'
}
require_command() {
  local command_name=$1
  if command -v "$command_name" >/dev/null 2>&1; then
    pass "command $command_name is available"
  else
    fail "command $command_name is unavailable"
  fi
}
validate_effective_config() {
  local line key value mode owner
  local -a environment_assignments=()

  if [[ ! -r "$effective_env_file" ]]; then
    fail "effective environment file is unreadable: $effective_env_file"
    return
  fi
  if [[ "$(id -u)" != 0 ]]; then
    fail "effective environment validation requires root to read $effective_env_file"
    return
  fi
  owner=$(stat -c '%u' "$effective_env_file")
  mode=$(stat -c '%a' "$effective_env_file")
  if [[ "$owner" != 0 ]] || (( (8#$mode & 8#022) != 0 )); then
    fail "effective environment file must be root-owned and not group/world writable: $effective_env_file"
    return
  fi
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ -z "$line" || "$line" == \#* || "$line" == \;* ]] && continue
    if [[ ! "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=([^\ \"\'\\\\]*)$ ]]; then
      fail "cannot safely parse EnvironmentFile line; use unquoted KEY=VALUE assignments: $effective_env_file"
      return
    fi
    key=${BASH_REMATCH[1]}
    value=${BASH_REMATCH[2]}
    environment_assignments+=("$key=$value")
  done < "$effective_env_file"
  if ! command -v runuser >/dev/null 2>&1; then
    fail "runuser is unavailable; cannot validate effective configuration as netpulse"
  elif runuser -u netpulse -- env -i "PATH=$PATH" "HOME=/var/lib/netpulse-agent" \
    "${environment_assignments[@]}" "$agent_bin" --config "$config_path" validate-config; then
    pass "effective agent configuration validates with $effective_env_file"
  else
    fail "effective agent configuration does not validate with $effective_env_file"
  fi
}

model_file=$(root_file /proc/device-tree/model)
if [[ -r "$model_file" ]]; then
  model=$(tr '\0' ' ' < "$model_file")
  if [[ "$model" == Raspberry\ Pi\ 3\ Model\ B\ Plus* ]]; then
    pass "hardware model: $model"
  else
    fail "requires Raspberry Pi 3 Model B+; observed: $model"
  fi
else
  fail "cannot read hardware model at $model_file"
fi

if command -v getconf >/dev/null 2>&1 && [[ "$(getconf LONG_BIT)" == 64 ]]; then
  pass "64-bit userspace"
else
  fail "requires a 64-bit userspace (getconf LONG_BIT must be 64)"
fi

os_id=$(os_value ID || true)
os_codename=$(os_value VERSION_CODENAME || true)
if [[ "$os_id" == debian && "$os_codename" == trixie ]]; then
  pass "OS metadata: Debian/Raspberry Pi OS Trixie"
else
  fail "requires Raspberry Pi OS Lite Trixie-compatible metadata; observed ID=${os_id:-missing} VERSION_CODENAME=${os_codename:-missing}"
fi

if command -v python3 >/dev/null 2>&1; then
  python_version=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
  case "$python_version" in
    3.12|3.13) pass "Python $python_version is supported" ;;
    *) fail "requires Python 3.12 or 3.13; observed: $python_version" ;;
  esac
else
  fail "python3 is unavailable"
fi

if command -v systemctl >/dev/null 2>&1 && systemctl --version >/dev/null 2>&1; then
  pass "systemd is available"
else
  fail "systemd is unavailable"
fi

require_command ping
require_command iw

if [[ "$skip_agent_check" == false ]]; then
  config_path=${NETPULSE_PI_PREFLIGHT_CONFIG:-/etc/netpulse-agent/agent.yaml}
  agent_bin=${NETPULSE_PI_PREFLIGHT_AGENT_BIN:-netpulse-agent}
  if ! command -v "$agent_bin" >/dev/null 2>&1; then
    fail "$agent_bin is unavailable; install the application before final preflight"
  elif [[ ! -r "$config_path" ]]; then
    fail "agent configuration is unreadable: $config_path"
  elif [[ -n "$effective_env_file" ]]; then
    validate_effective_config
  elif "$agent_bin" --config "$config_path" validate-config; then
    pass "agent configuration validates: $config_path"
  else
    fail "agent configuration does not validate: $config_path"
  fi
fi

if ((failures)); then
  printf 'Preflight failed: %d check(s) require attention.\n' "$failures" >&2
  exit 1
fi

printf 'Preflight passed. This only verifies the machine observed by this command.\n'
