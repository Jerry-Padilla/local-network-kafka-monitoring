"""Validated request filters and response contracts for daily reliability."""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints, model_validator


class SourceKind(StrEnum):
    NETWORK_MEASUREMENT = "network_measurement"
    SERVICE_CHECK = "service_check"


Identifier = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]
Count = Annotated[int, Field(ge=0, strict=True)]


class DailyReliabilityFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_date: date | None = None
    through_date: date | None = None
    agent_id: Identifier | None = None
    endpoint_id: Identifier | None = None
    source_kind: SourceKind | None = None
    probe_type: Identifier | None = None

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if (self.from_date is None) != (self.through_date is None):
            raise ValueError("from_date and through_date must be provided together")
        if self.from_date is not None and self.through_date is not None:
            if self.from_date > self.through_date:
                raise ValueError("from_date must not follow through_date")
            if (self.through_date - self.from_date).days + 1 > 366:
                raise ValueError("date range must not exceed 366 days")
        return self

    def fingerprint_payload(self) -> dict[str, str | None]:
        """Return the effective filters in stable order for cursor fingerprinting."""
        return {
            "from_date": self.from_date.isoformat() if self.from_date else None,
            "through_date": self.through_date.isoformat() if self.through_date else None,
            "agent_id": self.agent_id,
            "endpoint_id": self.endpoint_id,
            "source_kind": self.source_kind.value if self.source_kind else None,
            "probe_type": self.probe_type,
        }


class CursorKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_utc: date
    agent_id: Identifier
    endpoint_id: Identifier
    source_kind: SourceKind
    probe_type: Identifier


class DailyReliabilityRow(CursorKey):
    total_count: Count
    success_count: Count
    failure_count: Count
    success_rate_pct: FiniteFloat | None
    latency_count: Count
    latency_sum_ms: FiniteFloat | None
    mean_latency_ms: FiniteFloat | None
    packet_loss_count: Count
    packet_loss_sum_pct: FiniteFloat | None
    mean_packet_loss_pct: FiniteFloat | None


class DailyReliabilityPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[DailyReliabilityRow]
    next_cursor: str | None
    limit: Annotated[int, Field(ge=1, le=200, strict=True)]
