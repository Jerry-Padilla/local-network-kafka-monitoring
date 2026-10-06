from __future__ import annotations

import os
import sys


def configure_pyspark_python() -> None:
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


configure_pyspark_python()
