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


def test_phase3_migration_has_replay_safe_streaming_keys_and_ranges() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0003_phase3_streaming_metrics.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "0002"' in migration
    assert "network_window_metrics" in migration
    assert "stream_processing_failures" in migration
    assert "UNIQUE (source_topic, source_partition, source_offset)" in migration
    assert "window_size_seconds IN (60, 300, 900, 86400)" in migration


def test_phase4_migration_has_lifecycle_constraints_and_durable_outbox() -> None:
    migration = (
        Path(__file__).parents[1]
        / "migrations"
        / "versions"
        / "0004_phase4_incident_classification.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "0003"' in migration
    assert "network_incidents" in migration
    assert "incident_state_events" in migration
    assert "uq_network_incidents_active_key" in migration
    assert "published_at IS NULL" in migration
    assert "status = 'resolved' AND end_time IS NOT NULL" in migration


def test_phase5a_migration_has_grains_views_and_restricted_role() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0005_phase5a_analytics.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision = "0004"' in migration
    for name in (
        "dim_agent",
        "dim_endpoint",
        "dim_date",
        "dim_probe",
        "fact_reliability_daily",
        "fact_incident",
        "bridge_incident_agent",
        "bridge_incident_endpoint",
        "analytics_job_runs",
        "v_daily_probe_reliability",
        "v_incident_summary",
    ):
        assert name in migration
    assert "CREATE ROLE netpulse_report NOLOGIN" in migration
    assert "GRANT SELECT ON v_daily_probe_reliability, v_incident_summary" in migration
