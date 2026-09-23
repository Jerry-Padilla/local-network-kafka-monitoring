import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ROLES = {
    "data_engineer": ("gpt-5.6-sol", "medium"),
    "platform_pi_engineer": ("gpt-5.6-terra", "medium"),
    "verifier": ("gpt-5.6-terra", "high"),
}


def read_toml(relative_path: str) -> dict[str, object]:
    return tomllib.loads((ROOT / relative_path).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name,expected", ROLES.items())
def test_agent_role(name: str, expected: tuple[str, str]) -> None:
    config = read_toml(f".codex/agents/{name}.toml")
    assert config["name"] == name
    assert all(
        isinstance(config[key], str) and config[key].strip()
        for key in ("name", "description", "developer_instructions")
    )
    assert (config["model"], config["model_reasoning_effort"]) == expected
    if name == "verifier":
        assert config["sandbox_mode"] == "read-only"


def test_role_names_are_unique() -> None:
    role_files = sorted((ROOT / ".codex/agents").glob("*.toml"))
    assert {path.stem for path in role_files} == set(ROLES)
    names = [tomllib.loads(path.read_text(encoding="utf-8"))["name"] for path in role_files]
    assert len(set(names)) == len(ROLES)


def test_concurrency_limit() -> None:
    config = read_toml(".codex/config.toml")
    assert config["agents"]["max_concurrent_threads_per_session"] == 3
