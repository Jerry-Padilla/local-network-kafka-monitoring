from pathlib import Path


def test_initial_migration_contains_replay_and_quality_constraints() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0001_phase1_operational_schema.py"
    ).read_text(encoding="utf-8")

    assert "event_id UUID PRIMARY KEY" in migration
    assert "UNIQUE (source_topic, source_partition, source_offset)" in migration
    assert "packet_loss_pct >= 0 AND packet_loss_pct <= 100" in migration
    assert "processing_failures" in migration
