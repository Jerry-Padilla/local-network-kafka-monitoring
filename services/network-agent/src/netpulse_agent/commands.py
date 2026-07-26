"""Safe subprocess execution without shell interpolation."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CommandResult:
    return_code: int
    stdout: str
    stderr: str


CommandRunner = Callable[[list[str], float], CommandResult]


def run_command(arguments: list[str], timeout_seconds: float) -> CommandResult:
    """Run an explicit argument vector and capture bounded textual output."""
    completed = subprocess.run(
        arguments,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)
