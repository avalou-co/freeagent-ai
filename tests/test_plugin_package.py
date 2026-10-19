import json
import runpy
from pathlib import Path
from zipfile import ZipFile

import pytest

BUILD = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/package_hosted_plugin.py"))["build"]


def test_hosted_archive_is_reproducible_and_contains_resolvable_skill_references(tmp_path):
    first, second = tmp_path / "first.zip", tmp_path / "second.zip"
    BUILD(first, "synthetic-client")
    BUILD(second, "synthetic-client")
    assert first.read_bytes() == second.read_bytes()
    with ZipFile(first) as archive:
        names = archive.namelist()
        assert "skills/receipts/SKILL.md" in names
        assert "docs/receipts.md" in names
        assert len([name for name in names if name.endswith("SKILL.md")]) == 10
        assert all(name in {"plugin.json", "mcp.json"} or name.startswith(("skills/", "docs/")) for name in names)
        server = json.loads(archive.read("mcp.json"))["mcpServers"]["freeagent"]
        assert server["type"] == "streamable-http"
        assert "command" not in server
        auth = server["extensions"]["com.openai"]["auth"]
        assert auth["client"]["clientId"] == "synthetic-client"
        assert "clientSecret" not in auth["client"]
        for name in names:
            if name.endswith("SKILL.md"):
                text = archive.read(name).decode()
                assert "../../../docs/" not in text
                assert "../../docs/agent-rules.md" in text
                assert "docs/agent-rules.md" in names
    with pytest.raises(FileExistsError):
        BUILD(first, "synthetic-client")


def test_empty_oauth_client_does_not_produce_a_package(tmp_path):
    output = tmp_path / "invalid.zip"
    with pytest.raises(ValueError):
        BUILD(output, "")
    assert not output.exists()
