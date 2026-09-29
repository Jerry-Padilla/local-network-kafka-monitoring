from __future__ import annotations

from typing import Any

import pytest
from netpulse_streaming.metrics import StreamingMetrics
from netpulse_streaming.sink import PostgresStreamingSink
from prometheus_client import CollectorRegistry, generate_latest


class OversizedBatch:
    def limit(self, _count: int) -> OversizedBatch:
        return self

    @staticmethod
    def collect() -> list[Any]:
        return [object(), object()]


def test_sink_fails_visibly_when_driver_bound_is_exceeded() -> None:
    registry = CollectorRegistry()
    sink = PostgresStreamingSink(
        "postgresql://unused", maximum_rows=1, metrics=StreamingMetrics(registry)
    )

    with pytest.raises(RuntimeError, match="maximum"):
        sink.write_metrics(OversizedBatch(), batch_id=0)

    output = generate_latest(registry).decode()
    assert (
        'netpulse_streaming_batches_total{outcome="failed",query_kind="metrics"} 1.0'
        in output
    )
