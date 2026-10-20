"""Build an allowlisted hosted plugin ZIP; deployment inputs stay outside source."""

import argparse
import json
import os
import re
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]


def build(output: Path, client_id: str) -> None:
    if not client_id.strip():
        raise ValueError("Set FREEAGENT_PLUGIN_CLIENT_ID to the registered OAuth client ID")
    manifest = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "freeagent-ai",
        "version": re.findall(r'^version = "([^"]+)"$', (ROOT / "pyproject.toml").read_text(), re.MULTILINE)[0],
        "description": "Manage FreeAgent timesheets, draft invoices, expenses, bills and reports through chat.",
        "homepage": "https://freeagent-ai.avalou.co",
        "repository": "https://github.com/avalou-co/freeagent-ai",
        "extensions": {
            "com.openai": {
                "interface": {
                    "displayName": "FreeAgent AI",
                    "shortDescription": "FreeAgent accounting workflows in chat",
                    "longDescription": (
                        "Connect your UK FreeAgent account to work with timesheets, draft invoices, "
                        "estimates, expenses, bills, bank reconciliation and reports. Sign in through "
                        "FreeAgent without creating a separate Avalou account. Review and approve "
                        "accounting changes before they are sent."
                    ),
                    "developerName": "Avalou",
                    "category": "Productivity",
                    "capabilities": ["Read", "Write"],
                    "websiteURL": "https://freeagent-ai.avalou.co",
                    "supportURL": "https://freeagent-ai.avalou.co/support",
                    "privacyPolicyURL": "https://freeagent-ai.avalou.co/privacy",
                    "termsOfServiceURL": "https://freeagent-ai.avalou.co/terms",
                    "defaultPrompt": ["Show my overdue invoices", "Help me log time to a project"],
                }
            }
        },
    }
    mcp = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
        "mcpServers": {
            "freeagent": {
                "type": "streamable-http",
                "url": "https://freeagent-ai.avalou.co/mcp",
                "extensions": {
                    "com.openai": {
                        "auth": {
                            "type": "oauth",
                            "client": {
                                "mode": "provided",
                                "clientId": client_id,
                                "tokenEndpointAuthMethod": "client_secret_basic",
                            },
                            "baseScopes": ["freeagent:read", "freeagent:write"],
                        }
                    }
                },
            }
        },
    }
    entries = {
        "plugin.json": (json.dumps(manifest, indent=2) + "\n").encode(),
        "mcp.json": (json.dumps(mcp, indent=2) + "\n").encode(),
    }
    # Explicit files only: never recursively archive the checkout, credentials or evidence.
    for name in ("agent-rules.md", "api-notes.md"):
        entries[f"docs/{name}"] = (ROOT / "docs" / name).read_bytes()
    for source in sorted((ROOT / ".agents/skills").glob("*/SKILL.md")):
        content = source.read_text().replace("../../../docs/", "../../docs/")
        content += (
            "\n## Hosted connection\n\n"
            "Use the installed plugin's FreeAgent MCP tools. If sign-in is required, use the host's "
            "Connect action to authorize FreeAgent and return here. Never ask the user to configure "
            "an MCP URL, tokens, environment variables, a CLI, or an Avalou account. "
            "Read ../../docs/agent-rules.md before acting and ../../docs/api-notes.md before writes.\n"
        )
        entries[f"skills/{source.parent.name}/SKILL.md"] = content.encode()
    # Refuse replacement and restrict local package access: it contains operator-supplied metadata.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as stream, ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for name, content in sorted(entries.items()):
            info = ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New ZIP path outside the public checkout")
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(ROOT):
        parser.error("Write the deployment-specific package outside the public checkout")
    build(args.output, os.environ.get("FREEAGENT_PLUGIN_CLIENT_ID", ""))
