"""Release metadata must agree across the Python and plugin distributions."""

import ast
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


def test_hosted_server_version_matches_python_package():
    tree = ast.parse((ROOT / "freeagent_ai/hosted_app.py").read_text())
    versions = [
        ast.literal_eval(keyword.value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Server"
        for keyword in node.keywords
        if keyword.arg == "version"
    ]
    assert versions == [project_version()], "Hosted MCP server version must match pyproject.toml"


def test_hosted_user_agent_version_matches_python_package():
    tree = ast.parse((ROOT / "freeagent_ai/hosted_client.py").read_text())
    user_agents = [
        ast.literal_eval(value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Dict)
        for key, value in zip(node.keys, node.values, strict=True)
        if isinstance(key, ast.Constant) and key.value == "User-Agent"
    ]
    assert user_agents == [f"FreeAgent-AI/{project_version()}"], "Hosted User-Agent must match pyproject.toml"
