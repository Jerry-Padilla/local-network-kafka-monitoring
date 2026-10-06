from __future__ import annotations

import os
import sys

import pytest

import conftest


def test_pyspark_defaults_to_the_active_python_interpreter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("PYSPARK_PYTHON", raising=False)
    monkeypatch.delenv("PYSPARK_DRIVER_PYTHON", raising=False)

    conftest.configure_pyspark_python()

    assert os.environ.get("PYSPARK_PYTHON") == sys.executable
    assert os.environ.get("PYSPARK_DRIVER_PYTHON") == sys.executable


def test_pyspark_preserves_explicit_python_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PYSPARK_PYTHON", "worker-python")
    monkeypatch.setenv("PYSPARK_DRIVER_PYTHON", "driver-python")

    conftest.configure_pyspark_python()

    assert os.environ["PYSPARK_PYTHON"] == "worker-python"
    assert os.environ["PYSPARK_DRIVER_PYTHON"] == "driver-python"
