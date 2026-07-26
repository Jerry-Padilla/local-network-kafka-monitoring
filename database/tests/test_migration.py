from pathlib import Path


def test_initial_migration_contains_replay_and_quality_constraints() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0001_phase1_operational_schema.py"
    ).read_text(encoding="utf-8")

    assert "event_id UUID PRIMARY KEY" in migration
    assert "UNIQUE (source_topic, source_partition, source_offset)" in migration
    assert "packet_loss_pct >= 0 AND packet_loss_pct <= 100" in migration
    assert "processing_failures" in migration


def test_phase2_migration_registers_second_external_endpoint() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0002_phase2_agent_references.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "0001"' in migration
    assert "'public-dns-b'" in migration
    assert "ON CONFLICT (endpoint_id) DO NOTHING" in migration
