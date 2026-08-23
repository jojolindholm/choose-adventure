"""Hermetic CLI tests for the `cya` entry point.

These run the real `choose_adventure.main` module in a subprocess and assert
on exit codes and output. No network access is required.
"""

from __future__ import annotations

import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "choose_adventure.main", *args],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


def test_help_exits_zero_and_lists_flags() -> None:
    result = _run("--help")
    assert result.returncode == 0
    assert "--model" in result.stdout
    assert "--base-url" in result.stdout
    assert "--db" in result.stdout


def test_version_prints_version() -> None:
    result = _run("--version")
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


def test_uncreatable_db_dir_exits_one_without_traceback() -> None:
    result = _run("--db", "/nonexistent-xy-qa/z.db")
    assert result.returncode == 1
    assert "cannot create database directory" in result.stderr
    assert "Traceback" not in result.stderr
