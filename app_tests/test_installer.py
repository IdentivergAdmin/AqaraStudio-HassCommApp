"""Isolated tests for the Supervisor one-shot integration installer."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "aqara_studio_installer" / "run.sh"


def _run(tmp_path: Path, *, replacement: bool = False) -> subprocess.CompletedProcess[str]:
    config = tmp_path / "homeassistant"
    options = tmp_path / "options.json"
    options.write_text(json.dumps({"replace_existing": replacement}), encoding="utf-8")
    env = dict(
        os.environ,
        HA_CONFIG_DIR=str(config),
        PAYLOAD_DIR=str(tmp_path / "payload"),
        APP_OPTIONS_PATH=str(options),
    )
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, text=True, capture_output=True, check=False
    )


@pytest.fixture
def installed_fixture(tmp_path: Path) -> Path:
    config = tmp_path / "homeassistant"
    config.mkdir()
    source = tmp_path / "payload"
    source.mkdir()
    (source / "manifest.json").write_text(
        '{"version":"0.1.0b1"}', encoding="utf-8"
    )
    (source / "__init__.py").write_text("# test payload\n", encoding="utf-8")
    (source / "config_flow.py").write_text("# test payload\n", encoding="utf-8")
    return tmp_path


def test_supervisor_metadata():
    repo = yaml.safe_load((ROOT / "repository.yaml").read_text())
    addon = yaml.safe_load((ROOT / "aqara_studio_installer" / "config.yaml").read_text())
    assert repo["name"]
    assert addon["slug"] == "aqara_studio_installer"
    assert addon["arch"] == ["amd64", "aarch64"]
    assert addon["startup"] == "once"
    assert addon["boot"] == "manual_only"
    assert addon["map"] == [{"type": "homeassistant_config", "read_only": False}]
    assert addon["options"]["replace_existing"] is False
    assert addon["schema"]["replace_existing"] == "bool"
    dockerfile = (ROOT / "aqara_studio_installer" / "Dockerfile").read_text()
    assert "FROM ghcr.io/home-assistant/base:3.24" in dockerfile
    assert "COPY rootfs/ /" in dockerfile
    assert "COPY run.sh /run.sh" in dockerfile


def test_first_install(installed_fixture: Path):
    result = _run(installed_fixture)
    assert result.returncode == 0, result.stderr
    installed = installed_fixture / "homeassistant/custom_components/aqara_studio"
    assert (installed / "manifest.json").is_file()
    assert "Restart Home Assistant Core" in result.stdout


def test_existing_install_not_overwritten_by_default(installed_fixture: Path):
    installed = installed_fixture / "homeassistant/custom_components/aqara_studio"
    installed.mkdir(parents=True)
    (installed / "do_not_modify").write_text("original", encoding="utf-8")
    result = _run(installed_fixture)
    assert result.returncode == 0
    assert (installed / "do_not_modify").read_text() == "original"
    assert "leaving it unchanged" in result.stdout


def test_replace_existing_makes_backup(installed_fixture: Path):
    installed = installed_fixture / "homeassistant/custom_components/aqara_studio"
    installed.mkdir(parents=True)
    (installed / "old").write_text("keep me", encoding="utf-8")
    result = _run(installed_fixture, replacement=True)
    assert result.returncode == 0, result.stderr
    assert (installed / "manifest.json").exists()
    assert not (installed / "old").exists()
    backups = list(
        (installed_fixture / "homeassistant/aqara_studio_installer_backups").glob(
            "*/old"
        )
    )
    assert len(backups) == 1
    assert backups[0].read_text() == "keep me"


def test_missing_payload_refuses_to_modify(installed_fixture: Path):
    (installed_fixture / "payload/config_flow.py").unlink()
    result = _run(installed_fixture)
    assert result.returncode != 0
    assert not (installed_fixture / "homeassistant/custom_components").exists()


def test_symlink_target_is_rejected(installed_fixture: Path):
    target = installed_fixture / "homeassistant/custom_components/aqara_studio"
    target.parent.mkdir(parents=True)
    target.symlink_to(installed_fixture / "payload", target_is_directory=True)
    result = _run(installed_fixture, replacement=True)
    assert result.returncode != 0
    assert target.is_symlink()


def test_payload_matches_native_integration():
    """A frozen identical copy ships inside the app's Docker build context."""
    source = ROOT / "custom_components" / "aqara_studio"
    packaged = ROOT / "aqara_studio_installer" / "rootfs" / "opt" / "aqara_studio"
    assert source.exists() and packaged.exists()
    src_files = {
        p.relative_to(source): p.read_bytes()
        for p in source.rglob("*")
        if p.is_file()
    }
    pkg_files = {
        p.relative_to(packaged): p.read_bytes()
        for p in packaged.rglob("*")
        if p.is_file()
    }
    assert src_files == pkg_files
