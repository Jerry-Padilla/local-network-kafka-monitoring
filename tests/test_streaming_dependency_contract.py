from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_pyspark_runtime_and_kafka_connector_versions_match() -> None:
    requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")
    project = tomllib.loads(
        (ROOT / "services" / "stream-processor" / "pyproject.toml").read_text(encoding="utf-8")
    )
    dockerfile = (ROOT / "services" / "stream-processor" / "Dockerfile").read_text(encoding="utf-8")

    requirement_version = re.search(r"^pyspark==(\S+)$", requirements, re.MULTILINE)
    project_pin = next(
        dependency
        for dependency in project["project"]["dependencies"]
        if dependency.startswith("pyspark==")
    )
    runtime_version = re.search(r"^ARG SPARK_VERSION=(\S+)$", dockerfile, re.MULTILINE)
    connector_version = re.search(r"spark-sql-kafka-0-10_2\.13:(\d+\.\d+\.\d+)", dockerfile)

    assert requirement_version is not None
    assert runtime_version is not None
    assert connector_version is not None
    assert {
        requirement_version.group(1),
        project_pin.removeprefix("pyspark=="),
        runtime_version.group(1),
        connector_version.group(1),
    } == {"4.2.0"}
