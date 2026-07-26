from __future__ import annotations

from typing import Any

import pytest
from netpulse_streaming.sink import PostgresStreamingSink


class OversizedBatch:
    def limit(self, _count: int) -> OversizedBatch:
        return self

    @staticmethod
    def collect() -> list[Any]:
        return [object(), object()]


def test_sink_fails_visibly_when_driver_bound_is_exceeded() -> None:
    sink = PostgresStreamingSink("postgresql://unused", maximum_rows=1)

    with pytest.raises(RuntimeError, match="maximum"):
        sink.write_metrics(OversizedBatch(), batch_id=0)
