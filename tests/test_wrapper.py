from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
import os
ENV = os.environ.copy()
ENV["PYTHONPATH"] = str(ROOT / "wrapper")


def run(*args):
    return subprocess.run([sys.executable, "-m", "loom_map.cli", *args], cwd=ROOT, env=ENV, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def test_help():
    result = run("--help")
    assert result.returncode == 0
    assert "Supported modes" in result.stdout
    assert "octilinear" in result.stdout


def test_version():
    result = run("--version")
    assert result.returncode == 0
    assert "loom-map 0.1.0" in result.stdout


def test_missing_gtfs():
    result = run("missing.zip")
    assert result.returncode == 1
    assert "does not exist" in result.stderr
