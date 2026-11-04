"""Distribution contract for a native HACS/Marketplace integration.

This repository must never reintroduce a Supervisor App or two independent
update mechanisms. It must be self-contained for third-party installation.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_native_hacs_release_contract():
    contract = json.loads((ROOT / "release_contract.json").read_text())
    manifest = json.loads(
        (ROOT / "custom_components/aqara_studio/manifest.json").read_text()
    )
    hacs = json.loads((ROOT / "hacs.json").read_text())
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())

    assert contract["distribution"] == "hacs-marketplace"
    assert contract["integration_domain"] == manifest["domain"] == "aqara_studio"
    assert (
        contract["github_release_tag"]
        == contract["native_integration_version"]
        == project["project"]["version"]
        == manifest["version"]
    )
    assert contract["minimum_home_assistant"] == hacs["homeassistant"]
    assert hacs["name"] == manifest["name"] == "Aqara Studio"
    assert manifest["config_flow"] is True
    assert manifest["documentation"].startswith("https://")
    assert manifest["issue_tracker"].startswith("https://")
    assert manifest["codeowners"]
    assert contract["requires_core_restart_after_python_update"] is True


def test_repo_only_ships_one_native_integration_no_supervisor_app():
    assert not (ROOT / "repository.yaml").exists()
    assert not (ROOT / "aqara_studio_installer").exists()
    assert not (ROOT / ".github/workflows/app-installer.yml").exists()
    assert not (ROOT / "app_tests/test_installer.py").exists()
    assert not (ROOT / "app_tests/test_release_contract.py").exists()
    components = list((ROOT / "custom_components").iterdir())
    assert [x.name for x in components if x.is_dir()] == ["aqara_studio"]
    assert (components[0] / "__init__.py").exists()
    assert (components[0] / "manifest.json").exists()
    assert (components[0] / "translations/en.json").exists()


def test_docs_direct_existing_installer_users_to_safe_hacs_migration():
    readme = (ROOT / "README.md").read_text()
    migration = (ROOT / "docs/MIGRATE_LEGACY_INSTALLER.md").read_text()
    release_doc = (ROOT / "docs/RELEASE_VERIFICATION.md").read_text()
    contract = json.loads((ROOT / "release_contract.json").read_text())

    assert "HACS" in readme and "Marketplace" in readme
    assert "Settings → Marketplace" in readme
    assert "Tools → States" in readme
    assert "Apps → Repositories" not in readme
    assert "supervisor_add_addon_repository" not in readme
    assert "MIGRATE_LEGACY_INSTALLER.md" in readme
    assert "Do not" in migration and "config entry" in migration
    assert "custom_components/aqara_studio" in migration
    assert "Pre-release" in migration
    assert contract["legacy_installer_branch"] in migration
    assert "GitHub" in release_doc
    assert "hacs.json" in release_doc
    assert contract["github_release_tag"] in release_doc
    assert "0.1.5" not in (ROOT / "hacs.json").read_text()


def test_release_workflow_is_gated_and_never_restores_two_installers():
    workflow = (ROOT / ".github/workflows/release.yml").read_text()
    notes = (ROOT / "docs/RELEASE_NOTES.md").read_text()
    contract = json.loads((ROOT / "release_contract.json").read_text())
    assert "gh release create" in workflow
    assert "--prerelease" in workflow
    assert "python -m pytest" in workflow
    assert "ruff check" in workflow
    assert "hacs/action@" in workflow
    assert "hassfest@" in workflow
    assert "contents: write" in workflow
    assert "needs: [test, validate]" in workflow
    assert contract["github_release_tag"] in notes
    assert "App" in notes
    assert "Home Assistant Core" in notes
