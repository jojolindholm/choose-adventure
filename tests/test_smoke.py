import subprocess
import sys


def test_help_exits_zero():
    result = subprocess.run(
        [sys.executable, "-m", "choose_adventure.main", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "--model" in result.stdout
    assert "--base-url" in result.stdout
    assert "--db" in result.stdout


def test_version():
    result = subprocess.run(
        [sys.executable, "-m", "choose_adventure.main", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "0.1.0" in result.stdout


def test_missing_db_value_exits_nonzero():
    """Failure scenario: --db without value should exit non-zero with usage message, no traceback."""
    result = subprocess.run(
        [sys.executable, "-m", "choose_adventure.main", "--db"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "Traceback" not in result.stderr
