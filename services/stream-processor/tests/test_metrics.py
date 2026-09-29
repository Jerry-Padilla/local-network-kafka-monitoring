from __future__ import annotations

import pytest
from netpulse_streaming import cli
from netpulse_streaming.config import StreamingConfig
from netpulse_streaming.metrics import StreamingMetrics
from prometheus_client import CollectorRegistry, generate_latest


def test_streaming_metrics_cover_batch_outcomes_rows_duration_and_success() -> None:
    registry = CollectorRegistry()
    metrics = StreamingMetrics(registry)

    metrics.record_batch(
        "metrics", "succeeded", rows=4, duration_seconds=0.4, timestamp_seconds=100
    )
    metrics.record_batch("failures", "failed", rows=2, duration_seconds=0.2)

    output = generate_latest(registry).decode()
    assert (
        'netpulse_streaming_batches_total{outcome="succeeded",query_kind="metrics"} 1.0' in output
    )
    assert 'netpulse_streaming_batches_total{outcome="failed",query_kind="failures"} 1.0' in output
    assert 'netpulse_streaming_rows_total{row_kind="accepted"} 4.0' in output
    assert 'netpulse_streaming_rows_total{row_kind="rejected"} 2.0' in output
    assert 'netpulse_streaming_batch_duration_seconds_count{query_kind="metrics"} 1.0' in output
    assert 'netpulse_streaming_last_success_timestamp_seconds{query_kind="metrics"} 100.0' in output


def test_streaming_metrics_reject_unbounded_labels() -> None:
    metrics = StreamingMetrics(CollectorRegistry())

    with pytest.raises(ValueError, match="query kind"):
        metrics.record_batch("event-id", "succeeded", 1, 0.1)
    with pytest.raises(ValueError, match="batch outcome"):
        metrics.record_batch("metrics", "database unavailable", 1, 0.1)


@pytest.mark.parametrize("trigger_mode", ["processing-time", "available-now"])
def test_streaming_run_stops_metrics_server_for_each_trigger_mode(
    monkeypatch: pytest.MonkeyPatch,
    trigger_mode: str,
) -> None:
    monkeypatch.setenv("NETPULSE_STREAM_TRIGGER_MODE", trigger_mode)
    config = StreamingConfig.from_env()

    class FakeSparkContext:
        def setLogLevel(self, _level: str) -> None:
            return None

    class FakeSpark:
        sparkContext = FakeSparkContext()

        def __init__(self) -> None:
            self.stopped = False

        def stop(self) -> None:
            self.stopped = True

    class FakeQuery:
        isActive = False
        lastProgress = None
        name = "test-query"

        def awaitTermination(self) -> None:
            return None

        def stop(self) -> None:
            return None

    class FakeMetricsServer:
        latest = None

        def __init__(self, _config, _registry) -> None:
            self.calls: list[str] = []
            type(self).latest = self

        def start(self) -> None:
            self.calls.append("start")

        def stop(self) -> None:
            self.calls.append("stop")

    spark = FakeSpark()
    monkeypatch.setattr(cli, "build_spark", lambda _config: spark)
    monkeypatch.setattr(cli, "build_kafka_source", lambda *_args: object())
    monkeypatch.setattr(cli, "split_measurements", lambda _source: (object(), object()))
    monkeypatch.setattr(cli, "aggregate_measurements", lambda *_args: object())
    monkeypatch.setattr(cli, "_start_query", lambda *_args: FakeQuery())
    monkeypatch.setattr(cli, "MetricsServer", FakeMetricsServer)

    cli.run(config)

    assert spark.stopped is True
    assert FakeMetricsServer.latest.calls == ["start", "stop"]
