#!/usr/bin/env bash
set -euo pipefail

docker compose exec -T postgres \
  bash /docker-entrypoint-initdb.d/01-create-monitoring-users.sh
