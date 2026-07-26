from __future__ import annotations

import json
from pathlib import Path

from netpulse_agent.cli import main
from netpulse_agent.config import AgentConfig
from netpulse_agent.outbox import SQLiteOutbox
from netpulse_agent.runtime import build_collectors
from netpulse_agent.scheduler import CollectionErrorTracker

DISABLED_CONFIG = """
agent:
  agent_id: network-agent-wifi-01
  role: wifi_observer
outbox:
  path: {outbox_path}
collectors:
  router_ping:
    enabled: false
  external_ping:
    enabled: false
  dns:
    enabled: false
  http:
    enabled: false
  wifi:
    enabled: false
  heartbeat:
    enabled: false
  speed_test:
    enabled: false
"""


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "agent.yaml"
    path.write_text(
        DISABLED_CONFIG.format(outbox_path=(tmp_path / "outbox.db").as_posix()),
        encoding="utf-8",
    )
    return path


def test_cli_validates_and_reports_empty_outbox(tmp_path: Path, capsys) -> None:
    path = _write_config(tmp_path)

    assert main(["--config", str(path), "validate-config"]) == 0
    assert "configuration valid" in capsys.readouterr().out

    assert main(["--config", str(path), "outbox-status"]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["pending"] == 0
    assert status["delivered_retained"] == 0


def test_cli_collect_once_with_disabled_collectors_is_offline_safe(
    tmp_path: Path,
    capsys,
) -> None:
    path = _write_config(tmp_path)

    assert main(["--config", str(path), "collect-once"]) == 0

    result = json.loads(capsys.readouterr().out)
    assert result == {
        "acknowledged": 0,
        "enqueued": 0,
        "failed": 0,
        "outbox_depth": 0,
    }


def test_build_collectors_respects_every_enabled_flag(tmp_path: Path) -> None:
    config = AgentConfig.model_validate(
        {
            "agent": {
                "agent_id": "network-agent-wifi-01",
                "role": "wifi_observer",
            },
            "outbox": {"path": tmp_path / "outbox.db"},
            "collectors": {
                "router_ping": {"enabled": True, "endpoints": []},
                "external_ping": {"enabled": True, "endpoints": []},
                "dns": {"enabled": True, "endpoints": []},
                "http": {"enabled": True, "endpoints": []},
                "wifi": {"enabled": True},
                "heartbeat": {"enabled": True},
                "speed_test": {"enabled": True},
            },
        }
    )
    outbox = SQLiteOutbox(config.outbox)

    collectors = build_collectors(config, outbox, CollectionErrorTracker())

    assert [collector.name for collector in collectors] == [
        "router_ping",
        "external_ping",
        "dns",
        "http",
        "wifi",
        "heartbeat",
        "speed_test",
    ]
