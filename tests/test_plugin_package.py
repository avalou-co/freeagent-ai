import json
import re
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
        version = re.findall(
            r'^version = "([^"]+)"$',
            (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(),
            re.MULTILINE,
        )[0]
        assert json.loads(archive.read("plugin.json"))["version"] == version
        assert {name for name in names if name.endswith("SKILL.md")} == {
            f"skills/{source.parent.name}/SKILL.md"
            for source in (Path(__file__).resolve().parents[1] / ".agents/skills").glob("*/SKILL.md")
        }
        assert "docs/receipts.md" in names
        assert "docs/bank-attachments.md" in names
        assert "docs/receipt-review-cases.md" in names
        assert "skills/mileage/scripts/preview.py" not in names
        assert all(
            name in {"plugin.json", "mcp.json", "CANDIDATE-NOT-FOR-SUBMISSION.txt"}
            or name.startswith(("skills/", "docs/", "assets/"))
            for name in names
        )
        interface = json.loads(archive.read("plugin.json"))["extensions"]["com.openai"]["interface"]
        assert len(interface["shortDescription"]) <= 30
        assert interface["logo"] == "./assets/icon.png"
        assert archive.read("assets/icon.png").startswith(b"\x89PNG\r\n\x1a\n")
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


def test_operator_archive_matches_shared_named_tool_package_and_stays_private(tmp_path):
    import stat

    from freeagent_ai.public_package import package_files

    output = tmp_path / "candidate.zip"
    BUILD(output, "synthetic-client")
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    root = Path(__file__).resolve().parents[1]
    with ZipFile(output) as archive:
        assert archive.read("CANDIDATE-NOT-FOR-SUBMISSION.txt").startswith(b"Private operator candidate only")
        assert {
            name: archive.read(name) for name in archive.namelist() if name != "CANDIDATE-NOT-FOR-SUBMISSION.txt"
        } == package_files(root, {"mcp_client_id": "synthetic-client"})
        for name in archive.namelist():
            if name.endswith("SKILL.md"):
                text = archive.read(name).decode()
                assert not re.search(r"freeagent_(?:get|post|put|delete)\b", text)
                assert "../../docs/agent-rules.md" in text
                assert "../../docs/api-notes.md" in text


@pytest.mark.parametrize("name", ["add_missing_attachment", "remove_missing_attachment"])
def test_package_validates_attachment_tool_references(name):
    from freeagent_ai.public_package import validate_files

    with pytest.raises(ValueError, match="Unresolved packaged tool reference"):
        validate_files({"skills/bank-reconcile/SKILL.md": f"Use `{name}`".encode()})
