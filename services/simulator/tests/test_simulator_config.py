from netpulse_simulator.config import SimulatorConfig


def test_environment_overrides(monkeypatch) -> None:
    monkeypatch.setenv("KAFKA_BOOTSTRAP_SERVERS", "broker.example:9092")
    monkeypatch.setenv("NETPULSE_SIMULATOR_SEED", "99")

    config = SimulatorConfig.from_env()

    assert config.bootstrap_servers == "broker.example:9092"
    assert config.seed == 99
