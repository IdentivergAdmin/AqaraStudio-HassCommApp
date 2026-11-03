"""Standalone Supervisor one-shot installer tests (no Home Assistant runtime)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "aqara_studio_installer" / "run.sh"


def _write_integration(path: Path, version: str, *, domain: str = "aqara_studio") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "manifest.json").write_text(
        json.dumps({"domain": domain, "version": version}), encoding="utf-8"
    )
    (path / "__init__.py").write_text("# integration\n", encoding="utf-8")
    (path / "config_flow.py").write_text("# config flow\n", encoding="utf-8")


@pytest.fixture
def environment(tmp_path: Path) -> Path:
    (tmp_path / "homeassistant").mkdir()
    _write_integration(tmp_path / "payload", "0.1.2b1")
    return tmp_path


def _run(
    tmp_path: Path, *, path: str | None = None
) -> subprocess.CompletedProcess[str]:
    env = dict(
        os.environ,
        HA_CONFIG_DIR=str(tmp_path / "homeassistant"),
        PAYLOAD_DIR=str(tmp_path / "payload"),
        # No option file exists. Upgrades must not require saved UI toggles.
        APP_OPTIONS_PATH=str(tmp_path / "missing_options.json"),
    )
    if path is not None:
        env["PATH"] = path
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _installed(root: Path) -> Path:
    return root / "homeassistant/custom_components/aqara_studio"


def _backups(root: Path) -> list[Path]:
    folder = root / "homeassistant/aqara_studio_installer_backups"
    return sorted(p for p in folder.iterdir() if p.is_dir()) if folder.exists() else []


def test_supervisor_metadata_and_minimal_image():
    repo = yaml.safe_load((ROOT / "repository.yaml").read_text())
    addon = yaml.safe_load((ROOT / "aqara_studio_installer/config.yaml").read_text())
    assert repo["name"]
    assert addon["slug"] == "aqara_studio_installer"
    assert addon["version"] == "0.1.2"
    assert addon["arch"] == ["amd64", "aarch64"]
    assert addon["startup"] == "once"
    assert addon["boot"] == "manual_only"
    assert addon["init"] is True
    assert addon["map"] == [{"type": "homeassistant_config", "read_only": False}]
    assert addon["options"] == {}
    assert addon["schema"] is False
    dockerfile = (ROOT / "aqara_studio_installer/Dockerfile").read_text()
    assert "FROM alpine:3.24" in dockerfile
    assert "COPY rootfs/ /" in dockerfile
    assert "COPY run.sh /run.sh" in dockerfile


def test_first_install_no_options_needed(environment: Path):
    result = _run(environment)
    assert result.returncode == 0, result.stderr
    assert "FIRST INSTALL 0.1.2b1" in result.stdout
    assert "SUCCESS" in result.stdout
    assert (_installed(environment) / "manifest.json").exists()
    assert _backups(environment) == []


def test_upgrade_auto_backups_old_code_without_opt_in(environment: Path):
    installed = _installed(environment)
    _write_integration(installed, "0.1.1b1")
    (installed / "user_custom.py").write_text("preserve\n")
    # An option saved by v0.1.1 is explicitly ignored rather than blocking.
    (environment / "missing_options.json").write_text('{"replace_existing":false}')
    result = _run(environment)
    assert result.returncode == 0, result.stderr
    assert "UPGRADE 0.1.1b1 -> 0.1.2b1" in result.stdout
    assert "BACKUP:" in result.stdout
    assert "0.1.2b1" in (installed / "manifest.json").read_text()
    assert not (installed / "user_custom.py").exists()
    backups = _backups(environment)
    assert len(backups) == 1
    assert backups[0].name.startswith("aqara_studio_0.1.1b1_")
    assert (backups[0] / "user_custom.py").read_text() == "preserve\n"


def test_current_version_noop_even_with_old_true_option(environment: Path):
    installed = _installed(environment)
    _write_integration(installed, "0.1.2b1")
    (installed / "user_custom.py").write_text("retain")
    (environment / "missing_options.json").write_text('{"replace_existing":true}')
    result = _run(environment)
    assert result.returncode == 0
    assert "ALREADY CURRENT" in result.stdout
    assert "no restart needed" in result.stdout
    assert (installed / "user_custom.py").read_text() == "retain"
    assert _backups(environment) == []


@pytest.mark.parametrize(
    "version", ["0.1.2b2", "0.1.2rc1", "0.1.2", "0.2.0a1"]
)
def test_downgrades_are_blocked_without_touching_files(
    environment: Path, version: str
):
    installed = _installed(environment)
    _write_integration(installed, version)
    result = _run(environment)
    assert result.returncode != 0
    assert "DOWNGRADE BLOCKED" in result.stderr
    assert version in (installed / "manifest.json").read_text()
    assert _backups(environment) == []


@pytest.mark.parametrize("version", ["0.1.2a9", "0.1.1", "0.1.2b0"])
def test_older_release_prerelease_upgrade(environment: Path, version: str):
    installed = _installed(environment)
    _write_integration(installed, version)
    result = _run(environment)
    assert result.returncode == 0, result.stderr
    assert "UPGRADE" in result.stdout
    assert _backups(environment)


def test_missing_payload_does_not_change_installation(environment: Path):
    installed = _installed(environment)
    _write_integration(installed, "0.1.1b1")
    (environment / "payload/config_flow.py").unlink()
    result = _run(environment)
    assert result.returncode != 0
    assert "0.1.1b1" in (installed / "manifest.json").read_text()
    assert _backups(environment) == []


def test_bad_or_foreign_installed_manifest_does_not_get_overwritten(environment: Path):
    installed = _installed(environment)
    _write_integration(installed, "0.1.1b1", domain="other_integration")
    result = _run(environment)
    assert result.returncode != 0
    assert "existing integration manifest" in result.stderr.lower()
    assert "other_integration" in (installed / "manifest.json").read_text()
    assert _backups(environment) == []


@pytest.mark.parametrize("version", ["abc", "0.1.1.dev0", "10.2.4b"])
def test_invalid_installed_version_stays_untouched(environment: Path, version: str):
    installed = _installed(environment)
    _write_integration(installed, version)
    result = _run(environment)
    assert result.returncode != 0
    assert "Cannot compare" in result.stderr
    assert version in (installed / "manifest.json").read_text()


def test_reject_symlink_target(environment: Path):
    installed = _installed(environment)
    installed.parent.mkdir(parents=True)
    installed.symlink_to(environment / "payload", target_is_directory=True)
    result = _run(environment)
    assert result.returncode != 0
    assert installed.is_symlink()


def test_reject_symlink_backup_root(environment: Path):
    installed = _installed(environment)
    _write_integration(installed, "0.1.1b1")
    (environment / "homeassistant/aqara_studio_installer_backups").symlink_to(
        environment / "payload", target_is_directory=True
    )
    result = _run(environment)
    assert result.returncode != 0
    assert "0.1.1b1" in (installed / "manifest.json").read_text()


def test_failed_activation_restores_original(environment: Path):
    installed = _installed(environment)
    _write_integration(installed, "0.1.1b1")
    (installed / "unmodified.txt").write_text("original")
    fake_dir = environment / "fake_bin"
    fake_dir.mkdir()
    fake_mv = fake_dir / "mv"
    fake_mv.write_text(
        "#!/bin/sh\n"
        'case "${2:-}" in *".aqara_studio_stage."*) exit 41 ;; esac\n'
        'exec /bin/mv "$@"\n'
    )
    fake_mv.chmod(0o755)
    result = _run(environment, path=f"{fake_dir}:{os.environ['PATH']}")
    assert result.returncode != 0
    assert "automatic rollback attempted" in result.stderr
    assert (installed / "unmodified.txt").read_text() == "original"
    assert "0.1.1b1" in (installed / "manifest.json").read_text()


def test_payload_matches_native_integration():
    """The Docker package must be byte-for-byte identical to native source."""
    source = ROOT / "custom_components/aqara_studio"
    packaged = ROOT / "aqara_studio_installer/rootfs/opt/aqara_studio"
    assert source.exists() and packaged.exists()
    src_files = {
        p.relative_to(source): p.read_bytes() for p in source.rglob("*") if p.is_file()
    }
    pkg_files = {
        p.relative_to(packaged): p.read_bytes()
        for p in packaged.rglob("*")
        if p.is_file()
    }
    assert src_files == pkg_files
