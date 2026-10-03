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


def test_phase5b_migration_has_sre_views_roles_and_container_probe() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0006_phase5b_sre_views.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "0005"' in migration
    assert "CREATE VIEW v_sre_agent_status" in migration
    assert "CREATE VIEW v_sre_pipeline_status" in migration
    assert "LEFT JOIN LATERAL" in migration
    assert "ORDER BY h.event_time DESC, h.event_id DESC" in migration
    assert "dead_letter_published_at IS NULL" in migration
    assert "published_at IS NULL" in migration
    assert "CREATE ROLE netpulse_monitor NOLOGIN" in migration
    assert "GRANT pg_monitor TO netpulse_monitor" in migration
    assert "GRANT SELECT ON v_sre_agent_status, v_sre_pipeline_status" in migration
    assert "'container-observer-01', 'container_probe'" in migration


def test_phase6b_migration_exposes_only_safe_live_measurement_fields() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0007_phase6b_live_dashboard.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision = "0006"' in migration
    assert "CREATE VIEW v_grafana_live_measurements AS" in migration
    normalized_migration = " ".join(migration.split())
    expected_projection = (
        "CREATE VIEW v_grafana_live_measurements AS "
        "SELECT event_time, agent_id, target_id, measurement_type, success, "
        "latency_ms, packet_loss_pct, jitter_ms "
        "FROM network_measurements;"
    )
    assert expected_projection in normalized_migration
    assert "SELECT *" not in migration.upper()
    assert "GRANT SELECT ON v_grafana_live_measurements TO netpulse_report" in migration
    assert "REVOKE SELECT ON v_grafana_live_measurements FROM netpulse_report" in migration
    assert "DROP VIEW IF EXISTS v_grafana_live_measurements" in migration


def test_phase6b_migration_indexes_live_measurement_time_and_reverses_it() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0007_phase6b_live_dashboard.py"
    ).read_text(encoding="utf-8")

    assert (
        "CREATE INDEX idx_network_measurements_event_time "
        "ON network_measurements (event_time)" in " ".join(migration.split())
    )
    assert "DROP INDEX IF EXISTS idx_network_measurements_event_time" in migration


def test_phase6_query_api_migration_adds_reversible_mixed_direction_order_index() -> None:
    migration = (
        Path(__file__).parents[1] / "migrations" / "versions" / "0008_phase6_query_api_index.py"
    ).read_text(encoding="utf-8")

    normalized_migration = " ".join(migration.split())
    assert 'down_revision = "0007"' in migration
    assert (
        "CREATE INDEX idx_fact_reliability_daily_api_order "
        "ON fact_reliability_daily "
        "(date_utc DESC, agent_id ASC, endpoint_id ASC, source_kind ASC, probe_type ASC)"
        in normalized_migration
    )
    assert "DROP INDEX IF EXISTS idx_fact_reliability_daily_api_order" in migration


def test_monitoring_user_scripts_require_passwords_and_quote_psql_values() -> None:
    root = Path(__file__).parents[2]
    init_script = (root / "database" / "init" / "01-create-monitoring-users.sh").read_text(
        encoding="utf-8"
    )
    provision_script = (root / "scripts" / "provision-monitoring-users.sh").read_text(
        encoding="utf-8"
    )

    for variable in ("GRAFANA_POSTGRES_PASSWORD", "POSTGRES_EXPORTER_PASSWORD"):
        assert f"${{{variable}:-}}" in init_script
        assert f"--set {variable.lower()}=" not in init_script
    assert "format('ALTER ROLE netpulse_grafana LOGIN PASSWORD %L'" in init_script
    assert "'ALTER ROLE netpulse_postgres_exporter LOGIN PASSWORD %L'" in init_script
    assert ":'exporter_password'" in init_script
    assert "GRANT netpulse_report TO netpulse_grafana" in init_script
    assert "GRANT netpulse_monitor TO netpulse_postgres_exporter" in init_script
    assert "/docker-entrypoint-initdb.d/01-create-monitoring-users.sh" in provision_script
