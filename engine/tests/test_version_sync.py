"""Contract tests for the repository version synchronization utility."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parents[2] / "scripts" / "sync_version.py"


def write_fixture(root: Path, version: str) -> None:
    (root / "engine").mkdir()
    (root / "desktop" / "src-tauri").mkdir(parents=True)
    (root / "VERSION").write_text(version + "\n")
    (root / "engine" / "pyproject.toml").write_text(
        f'[project]\nname = "auvide"\nversion = "{version}"\n'
    )
    (root / "desktop" / "package.json").write_text(json.dumps({"version": version}))
    (root / "desktop" / "src-tauri" / "Cargo.toml").write_text(
        f'[package]\nname = "auvide"\nversion = "{version}"\n'
    )
    (root / "desktop" / "src-tauri" / "tauri.conf.json").write_text(
        json.dumps({"version": version})
    )


def run_sync(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_reports_matching_versions(tmp_path):
    write_fixture(tmp_path, "0.2.0")

    result = run_sync(tmp_path, "--check")

    assert result.returncode == 0
    assert "0.2.0" in result.stdout


def test_set_updates_every_consumer_and_canonical_file(tmp_path):
    write_fixture(tmp_path, "0.2.0")

    result = run_sync(tmp_path, "--set", "0.3.0")

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "VERSION").read_text().strip() == "0.3.0"
    assert 'version = "0.3.0"' in (tmp_path / "engine" / "pyproject.toml").read_text()
    assert json.loads((tmp_path / "desktop" / "package.json").read_text())["version"] == "0.3.0"
    assert 'version = "0.3.0"' in (tmp_path / "desktop" / "src-tauri" / "Cargo.toml").read_text()
    assert json.loads((tmp_path / "desktop" / "src-tauri" / "tauri.conf.json").read_text())["version"] == "0.3.0"


def test_check_reports_drift(tmp_path):
    write_fixture(tmp_path, "0.2.0")
    (tmp_path / "desktop" / "package.json").write_text(json.dumps({"version": "0.1.0"}))

    result = run_sync(tmp_path, "--check")

    assert result.returncode == 1
    assert "desktop/package.json" in result.stderr
