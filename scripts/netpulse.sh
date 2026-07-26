#!/usr/bin/env bash
set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose=(docker compose -f "$repository_root/docker-compose.yml")
command="${1:-config}"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker CLI was not found. Install Docker Engine/Desktop." >&2
  exit 1
fi

case "$command" in
  setup)
    [[ -f "$repository_root/.env" ]] || cp "$repository_root/.env.example" "$repository_root/.env"
    "${compose[@]}" build
    ;;
  lint)
    "${compose[@]}" --profile test run --rm --entrypoint ruff tests check .
    ;;
  format)
    "${compose[@]}" --profile test run --rm --entrypoint ruff tests format .
    ;;
  typecheck)
    "${compose[@]}" --profile test run --rm --entrypoint mypy tests
    ;;
  test|test-unit)
    "${compose[@]}" --profile test run --rm tests -p no:cacheprovider -m "not integration" --cov --cov-report=term-missing
    ;;
  test-integration)
    "${compose[@]}" up -d --wait event-ingestor
    "${compose[@]}" --profile test run --rm -e NETPULSE_INTEGRATION=1 tests -p no:cacheprovider -m integration
    ;;
  up)
    "${compose[@]}" up -d --build --wait event-ingestor
    ;;
  down)
    "${compose[@]}" down
    ;;
  reset)
    echo "Removing NetPulse containers and persistent Kafka/PostgreSQL volumes." >&2
    "${compose[@]}" down --volumes --remove-orphans
    ;;
  logs)
    "${compose[@]}" logs --follow --tail 200
    ;;
  demo)
    "${compose[@]}" up -d --build --wait event-ingestor
    "${compose[@]}" --profile demo run --rm simulator run --scenario healthy --duration 10
    "${compose[@]}" --profile demo run --rm simulator run --scenario wifi-degradation --duration 5
    "${compose[@]}" --profile test run --rm --entrypoint python tests scripts/verify_stack.py
    ;;
  verify)
    "${compose[@]}" up -d --build --wait event-ingestor
    "${compose[@]}" --profile demo run --rm simulator run --scenario malformed-events --duration 2
    "${compose[@]}" --profile test run --rm --entrypoint python tests scripts/verify_stack.py
    ;;
  kafka-topics)
    "${compose[@]}" exec -T kafka /opt/kafka/bin/kafka-topics.sh \
      --bootstrap-server localhost:9092 --describe
    ;;
  db-shell)
    "${compose[@]}" exec postgres psql -U netpulse_admin -d netpulse
    ;;
  config)
    "${compose[@]}" config --quiet
    ;;
  agent-build)
    "${compose[@]}" build network-agent
    ;;
  agent-validate)
    "${compose[@]}" --profile agent run --rm --no-deps network-agent \
      --config /etc/netpulse-agent/agent.yaml validate-config
    ;;
  agent-test)
    "${compose[@]}" --profile test run --rm tests -p no:cacheprovider \
      services/network-agent/tests
    ;;
  stream-build)
    "${compose[@]}" build stream-processor
    ;;
  stream-run)
    "${compose[@]}" up -d --build --wait event-ingestor
    "${compose[@]}" --profile streaming up -d --build stream-processor
    ;;
  stream-once)
    "${compose[@]}" up -d --build --wait event-ingestor
    "${compose[@]}" --profile streaming run --rm \
      -e NETPULSE_STREAM_TRIGGER_MODE=available-now stream-processor
    ;;
  stream-verify)
    "${compose[@]}" up -d --build --wait event-ingestor
    "${compose[@]}" --profile demo run --rm simulator \
      run --scenario healthy --duration 2 --seed 42
    "${compose[@]}" --profile demo run --rm simulator \
      run --scenario malformed-events --duration 1 --seed 43
    "${compose[@]}" --profile streaming run --rm \
      -e NETPULSE_STREAM_TRIGGER_MODE=available-now stream-processor
    "${compose[@]}" --profile test run --rm --entrypoint python \
      tests scripts/verify_streaming.py
    ;;
  *)
    echo "Unknown command: $command" >&2
    exit 2
    ;;
esac
