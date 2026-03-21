from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src")
    return subprocess.run(
        [sys.executable, "-m", "osk", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_doctor_reports_scaffold_ready() -> None:
    result = run_cli("doctor")

    assert result.returncode == 0
    assert "Osk scaffold status" in result.stdout
    assert "Scaffold ready for Phase 1 implementation work." in result.stdout


def test_start_reports_placeholder_status() -> None:
    result = run_cli("start")

    assert result.returncode == 1
    assert "'start' is planned but not implemented yet." in result.stdout
