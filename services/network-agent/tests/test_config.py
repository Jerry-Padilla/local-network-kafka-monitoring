from __future__ import annotations

from pathlib import Path

import pytest
from netpulse_agent.config import AgentConfigurationError, load_config
from netpulse_contracts.models import AgentRole

MINIMAL = """
agent:
  agent_id: network-agent-wifi-01
  role: wifi_observer
collectors:
  router_ping:
    endpoints: []
"""


def test_yaml_defaults_and_allowlisted_environment_overrides(tmp_path: Path) -> None:
    path = tmp_path / "agent.yaml"
    path.write_text(MINIMAL, encoding="utf-8")

    config = load_config(
        path,
        {
            "NETPULSE_AGENT_ID": "network-agent-ethernet-01",
            "NETPULSE_AGENT_ROLE": "wired_reference",
            "NETPULSE_OUTBOX_PATH": str(tmp_path / "custom.db"),
            "NETPULSE_OUTBOX_MAXIMUM_BYTES": "2097152",
            "UNRELATED": "ignored",
        },
    )

    assert config.agent.agent_id == "network-agent-ethernet-01"
    assert config.agent.role is AgentRole.WIRED_REFERENCE
    assert config.outbox.path == tmp_path / "custom.db"
    assert config.outbox.maximum_bytes == 2_097_152
    assert config.collectors.speed_test.enabled is False


@pytest.mark.parametrize(
    "content",
    [
        "[]",
        "agent:\n  agent_id: INVALID\n  role: wifi_observer\n",
        "agent:\n  agent_id: valid-agent\n  role: wifi_observer\nunknown: true\n",
        """
agent:
  agent_id: valid-agent
  role: wifi_observer
collectors:
  http:
    endpoints:
      - endpoint_id: unsafe
        address: file:///etc/passwd
""",
    ],
)
def test_invalid_configuration_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / "agent.yaml"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(AgentConfigurationError):
        load_config(path, {})
