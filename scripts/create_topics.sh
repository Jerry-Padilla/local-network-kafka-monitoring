#!/usr/bin/env bash
set -euo pipefail

bootstrap_servers="${KAFKA_BOOTSTRAP_SERVERS:-kafka:9092}"
kafka_topics="/opt/kafka/bin/kafka-topics.sh"
kafka_configs="/opt/kafka/bin/kafka-configs.sh"

ensure_topic() {
  local topic="$1"
  local retention_ms="$2"

  "$kafka_topics" \
    --bootstrap-server "$bootstrap_servers" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions 3 \
    --replication-factor 1 \
    --config "cleanup.policy=delete" \
    --config "retention.ms=$retention_ms"

  "$kafka_configs" \
    --bootstrap-server "$bootstrap_servers" \
    --alter \
    --entity-type topics \
    --entity-name "$topic" \
    --add-config "cleanup.policy=delete,retention.ms=$retention_ms"
}

seven_days=604800000
thirty_days=2592000000

ensure_topic "network.measurements.raw.v1" "$seven_days"
ensure_topic "network.measurements.valid.v1" "$seven_days"
ensure_topic "network.service-checks.raw.v1" "$seven_days"
ensure_topic "network.speed-tests.raw.v1" "$thirty_days"
ensure_topic "network.agent-heartbeats.v1" "$seven_days"
ensure_topic "network.incidents.v1" "$thirty_days"
ensure_topic "network.dead-letter.v1" "$thirty_days"
ensure_topic "network.processing-metrics.v1" "$seven_days"

"$kafka_topics" --bootstrap-server "$bootstrap_servers" --list
