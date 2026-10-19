"""Release metadata must agree across the Python and plugin distributions."""

import json
import re
from pathlib import Path

import pytest

from freeagent_ai.public_package import package_files

ROOT = Path(__file__).resolve().parents[1]


def project_version():
    # Keep this check runnable on Python 3.10 without an extra TOML dependency.
    versions = re.findall(r'^version = "([^"]+)"$', (ROOT / "pyproject.toml").read_text(), re.MULTILINE)
    assert len(versions) == 1
    assert re.fullmatch(r"\d+\.\d+\.\d+", versions[0])
    return versions[0]


@pytest.mark.parametrize("directory", [".claude-plugin", ".codex-plugin"])
def test_plugin_version_matches_python_package(directory):
    manifest = json.loads((ROOT / directory / "plugin.json").read_text())
    assert manifest["version"] == project_version()


def test_current_version_has_release_notes():
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert f"## [{project_version()}]" in changelog.splitlines()


def test_public_package_version_matches_python_package():
    manifest = json.loads(package_files(ROOT)["plugin.json"])
    assert manifest["version"] == project_version()
