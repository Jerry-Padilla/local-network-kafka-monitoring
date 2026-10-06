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
    "${compose[@]}" --profile test run --rm -e NETPULSE_INTEGRATION=1 tests \
      -p no:cacheprovider -m "integration and not api_integration and not host_integration"
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
  classifier-build)
    "${compose[@]}" build incident-classifier
    ;;
  classifier-run)
    "${compose[@]}" up -d --build --wait event-ingestor
    "${compose[@]}" --profile classification up -d --build incident-classifier
    ;;
  classifier-once)
    "${compose[@]}" up -d --build --wait event-ingestor
    "${compose[@]}" --profile classification run --rm --no-deps incident-classifier once
    ;;
  classifier-verify)
    "${compose[@]}" up -d --build --wait event-ingestor
    "${compose[@]}" build incident-classifier
    "${compose[@]}" --profile demo run --rm --no-deps simulator \
      run --scenario wifi-degradation --duration 3 --seed 71
    sleep 1
    for _ in 1 2; do
      "${compose[@]}" --profile classification run --rm --no-deps \
        -e NETPULSE_CLASSIFIER_LOOKBACK_SECONDS=15 incident-classifier once
    done
    "${compose[@]}" --profile demo run --rm --no-deps simulator \
      run --scenario healthy --duration 6 --seed 72
    sleep 1
    for _ in 1 2; do
      "${compose[@]}" --profile classification run --rm --no-deps \
        -e NETPULSE_CLASSIFIER_LOOKBACK_SECONDS=5 incident-classifier once
    done
    "${compose[@]}" --profile test run --rm --no-deps --entrypoint python \
      tests scripts/verify_classification.py
    ;;
  analytics-build)
    "${compose[@]}" --profile analytics build analytics
    ;;
  analytics-all)
    "${compose[@]}" up -d --wait postgres
    "${compose[@]}" --profile analytics build migrate analytics
    "${compose[@]}" run --rm migrate
    "${compose[@]}" --profile analytics run --rm analytics --all
    ;;
  analytics-verify)
    "${compose[@]}" up -d --wait postgres
    "${compose[@]}" --profile analytics --profile test build migrate analytics tests
    "${compose[@]}" run --rm migrate
    "${compose[@]}" --profile analytics run --rm analytics --all
    "${compose[@]}" --profile test run --rm --no-deps --entrypoint python \
      tests scripts/verify_analytics.py
    ;;
  api-build)
    "${compose[@]}" --profile api build migrate query-api
    ;;
  api-up)
    "${compose[@]}" up -d --wait postgres
    "${compose[@]}" --profile api build migrate query-api
    "${compose[@]}" run --rm --no-deps migrate
    "${compose[@]}" --profile api run --rm --no-deps query-api-init
    "${compose[@]}" --profile api up -d --no-deps --build --wait query-api
    ;;
  api-integration)
    "${compose[@]}" up -d --wait postgres
    "${compose[@]}" --profile api --profile test build migrate query-api tests
    "${compose[@]}" run --rm --no-deps migrate
    "${compose[@]}" --profile api run --rm --no-deps query-api-init
    "${compose[@]}" --profile api up -d --no-deps --build --wait query-api
    "${compose[@]}" --profile api --profile test run --rm --no-deps \
      -e NETPULSE_INTEGRATION=1 tests -p no:cacheprovider -m api_integration \
      tests/test_query_api_integration.py -q
    ;;
  api-provisioning-test)
    host_python=python3
    [[ ! -x "$repository_root/.venv/bin/python" ]] || host_python="$repository_root/.venv/bin/python"
    "$host_python" -m pytest -p no:cacheprovider -m host_integration \
      tests/test_query_api_provisioning_live.py -q
    ;;
  api-verify)
    "${compose[@]}" --profile api --profile test run --rm --no-deps \
      --entrypoint python tests scripts/verify_query_api.py \
      --base-url http://query-api:8000
    ;;
  api-down)
    "${compose[@]}" --profile api stop query-api query-api-init
    "${compose[@]}" --profile api rm -f query-api query-api-init
    ;;
  monitoring-render)
    [[ -n "${2:-}" ]] || { echo "monitoring-render requires the Pi IPv4 address or hostname" >&2; exit 2; }
    python "$repository_root/scripts/render_pi_metrics_target.py" "$2"
    ;;
  monitoring-up)
    "${compose[@]}" up -d --wait postgres
    "${compose[@]}" run --rm migrate
    "${compose[@]}" --profile monitoring rm -f monitoring-init
    "${compose[@]}" --profile monitoring run --rm monitoring-init
    "${compose[@]}" up -d --build --wait event-ingestor
    "${compose[@]}" --profile monitoring up -d --wait
    ;;
  monitoring-verify)
    python "$repository_root/scripts/verify_observability.py"
    ;;
  monitoring-down)
    monitoring_services=(grafana prometheus alertmanager kafka-exporter postgres-exporter)
    "${compose[@]}" --profile monitoring stop "${monitoring_services[@]}"
    "${compose[@]}" --profile monitoring rm -f "${monitoring_services[@]}"
    ;;
  failure-drill)
    python "$repository_root/scripts/failure_drills.py" "${2:-all}"
    ;;
  *)
    echo "Unknown command: $command" >&2
    exit 2
    ;;
esac
