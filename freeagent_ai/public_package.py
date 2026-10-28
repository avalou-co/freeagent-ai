"""Reproducible hosted package from canonical workflows; release builds fail closed.

Draft archives are for review only. Credentials never enter either archive. Run with
python -m freeagent_ai.public_package --draft --output build/freeagent-ai-draft.zip.
"""

import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path

from .hosted_auth import ORIGIN
from .package_contract import coverage, validate_contract, validate_workflow
from .public_tools import REGISTRY, RESOURCES, audit

VERSION = "0.4.0"


def render_hosted(text, *, docs_prefix="../../docs/"):
    if "## Hosted transport" in text:
        raise ValueError("Hosted transport heading is reserved for the generated inventory")
    if docs_prefix == "../../docs/" and re.search(r"freeagent_(?:get|post|put|delete)\b", text):
        raise ValueError("Canonical workflow requires a local generic executor")
    # Preserve the canonical business/approval prose. Replace transport-specific instructions
    # deterministically; the appendix defines exact declared read/correction tool mappings.
    text = text.replace("../../../docs/", "../../docs/").replace(
        "../../../publication/receipt-review-cases.md", "../../docs/receipt-review-cases.md"
    )
    text = text.replace("../.agents/skills/", "../skills/")
    text = text.replace(
        "mcp.md#correcting-entries-created-in-a-task",
        "agent-rules.md#correcting-entries-created-in-the-current-task",
    )
    text = text.replace("receipt_path", "receipt").replace("attachment_path", "attachment")
    for name in ["freeagent_get", "freeagent_post", "freeagent_put", "freeagent_delete"]:
        replacement = "the matching named read tool" if name.endswith("get") else "the matching named write tool"
        text = text.replace(name, replacement)
    text = text.replace("GET expenses/mileage_settings", "get_mileage_settings")
    for endpoint, (root, _) in sorted(RESOURCES.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(r"GET\s+" + endpoint + r"(?:/<id>)?", "get_" + root + " or list_" + endpoint, text)
    text = text.replace("accounting/profit_and_loss/summary", "get_profit_and_loss")
    text = text.replace("accounting/trial_balance/summary", "get_trial_balance")
    text = text.replace("accounting/balance_sheet", "get_balance_sheet")
    return (
        text
        + """

## Hosted transport

Use the host's Connect action when sign-in is required. Never ask the user to configure
an MCP URL, tokens, environment variables, a CLI, or an Avalou account.
Use only the named tools in the mapping below, never an API path or local file.
Supply numeric IDs for top-level resource-reference parameters. Nested provider payloads
(such as create_expense_from_payload.expense) keep full resource URLs returned by
provider reads, as their tool descriptions specify. Query examples above describe
provider filters; use only the parameters declared by the named tool. When the provider
does not support a filter, filter retrieved results and say so. Do not infer completeness
after a read error or silently drop accounting fields needed by the user's request.
Receipt/attachment inputs are ChatGPT file objects, not local paths.
Preserve the write preview, user approval, current-request ownership and readback rules.
`confirmed` is an assertion of obtained user approval, not a replacement for approval.
Corrections use the individually declared update/delete tool for that resource.
Never retry an uncertain write. After linking/replacement, sign in again and reconnect.
ChatGPT authorization lasts up to 30 days with automatic token renewal. Ask for business-specific defaults; never guess.

"""
        + f"Read {docs_prefix}agent-rules.md before acting and {docs_prefix}api-notes.md before writes.\n\n"
        + "\n".join(f"- `{op.name}`: {op.method} {op.endpoint}" for op in REGISTRY.values())
        + "\n"
    )


def package_files(root, metadata=None):
    metadata = metadata or {}
    allowed_interface = {
        "displayName",
        "shortDescription",
        "longDescription",
        "developerName",
        "category",
        "capabilities",
        "websiteURL",
        "supportURL",
        "privacyPolicyURL",
        "termsOfServiceURL",
        "defaultPrompt",
        "composerIcon",
        "logo",
        "screenshots",
    }
    if (
        set(metadata) - {"interface", "mcp_client_id", "evidence"}
        or set(metadata.get("interface", {})) - allowed_interface
    ):
        raise ValueError("Publication metadata contains unsupported fields; credentials are not accepted")
    interface = {
        "displayName": "FreeAgent AI by Avalou",
        "shortDescription": "FreeAgent accounting in chat",
        "logo": "./assets/icon.png",
        "composerIcon": "./assets/icon.png",
        "longDescription": "By Avalou. An independent integration for FreeAgent. Connect your own UK FreeAgent account to log time, create draft invoices and estimates, record expenses and bills, reconcile banking and read reports. Writes require approval and verification.",
        "developerName": "Avalou",
        "category": "Productivity",
        "capabilities": [
            "Timesheets",
            "Draft invoices",
            "Expenses",
            "Mileage",
            "Estimates",
            "Bills",
            "Bank reconciliation",
            "Reports",
            "Invoice status",
        ],
        "websiteURL": ORIGIN,
        "supportURL": ORIGIN + "/support",
        "privacyPolicyURL": ORIGIN + "/privacy",
        "termsOfServiceURL": ORIGIN + "/terms",
        "defaultPrompt": [
            "What invoices are overdue?",
            "Prepare my timesheets for last week.",
            "Show my profit and loss for the dates I provide.",
        ],
        **metadata.get("interface", {}),
    }
    manifest = {
        "$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        "name": "freeagent-ai",
        "version": VERSION,
        "description": "FreeAgent API workflows with per-user account linking.",
        "author": {"name": "Avalou", "url": "https://avalou.co"},
        "repository": "https://github.com/avalou-co/freeagent-ai",
        "extensions": {"com.openai": {"interface": interface}},
    }
    auth = {
        "type": "oauth",
        "client": {
            "mode": "provided",
            "clientId": metadata.get("mcp_client_id", "SET_AFTER_AUTH0_SETUP"),
            "tokenEndpointAuthMethod": "client_secret_basic",
        },
        "baseScopes": ["freeagent:read", "freeagent:write"],
    }
    files = {
        "plugin.json": json.dumps(manifest, indent=2).encode(),
        "mcp.json": json.dumps(
            {
                "$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                "mcpServers": {
                    "freeagent": {
                        "type": "streamable-http",
                        "url": ORIGIN + "/mcp",
                        "extensions": {"com.openai": {"auth": auth}},
                    }
                },
            },
            indent=2,
        ).encode(),
        "docs/public-tool-audit.json": json.dumps(audit(), indent=2, sort_keys=True).encode(),
    }
    sources = {}
    for source in sorted((root / ".agents/skills").glob("*/SKILL.md")):
        files[f"skills/{source.parent.name}/SKILL.md"] = render_hosted(source.read_text()).encode()
        sources[str(source.relative_to(root))] = hashlib.sha256(source.read_bytes()).hexdigest()
    for name in [
        "agent-rules.md",
        "api-notes.md",
        "receipts.md",
        "bank-attachments.md",
        "tax-overview.md",
        "credit-notes.md",
        "analysis.md",
        "invoicing.md",
        "documents.md",
        "recurring-revenue.md",
        "marketplace-contract.md",
    ]:
        source = root / "docs" / name
        files["docs/" + name] = render_hosted(source.read_text(), docs_prefix="").encode()
        sources[str(source.relative_to(root))] = hashlib.sha256(source.read_bytes()).hexdigest()
    case_source = root / "publication/receipt-review-cases.md"
    files["docs/receipt-review-cases.md"] = case_source.read_bytes()
    sources[str(case_source.relative_to(root))] = hashlib.sha256(case_source.read_bytes()).hexdigest()
    files["docs/source-digests.json"] = json.dumps(sources, sort_keys=True, indent=2).encode()
    for path in sorted((root / "publication/assets").glob("*.png")):
        if path.is_symlink() or not path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise ValueError("Invalid publication image")
        files["assets/" + path.name] = path.read_bytes()
    validate_files(files, root=root)
    files["docs/capabilities.json"] = json.dumps(coverage(files), indent=2, sort_keys=True).encode()
    return files


def validate_files(files, *, root=None):
    """Every archive mode shares the executable-workflow and reference gate."""
    for path, data in files.items():
        if path.startswith("skills/") and path.endswith(".md"):
            validate_workflow(path, data.decode())
        if re.search(rb"freeagent_(?:get|post|put|delete)\b", data):
            raise ValueError("Local generic executor leaked into hosted package")
    if "plugin.json" in files:
        validate_contract(files, root=root)


def build(root, output, *, draft=False, metadata=None):
    if not draft:
        if not metadata or not metadata.get("mcp_client_id"):
            raise ValueError("Create Auth0 and supply public MCP client ID before a release build")
        gates = [
            "publisher_verified",
            "policies_approved",
            "security_review_passed",
            "reviewer_cases_passed",
            "mobile_verified",
            "domain_verified",
        ]
        if any(metadata.get("evidence", {}).get(gate) is not True for gate in gates):
            raise ValueError("Publication evidence incomplete; use --draft for review only")
        interface = metadata.get("interface", {})
        if not all(interface.get(name) for name in ["composerIcon", "logo", "screenshots"]):
            raise ValueError("Supply real publication icons and screenshots before release")
    files = package_files(root, metadata)
    if not draft:
        assert metadata is not None
        interface = metadata["interface"]
        screenshots = interface["screenshots"]
        if not isinstance(screenshots, list) or not screenshots:
            raise ValueError("Screenshots must be packaged asset paths")
        for path in [interface["composerIcon"], interface["logo"], *screenshots]:
            if not isinstance(path, str) or not path.startswith("./assets/") or path[2:] not in files:
                raise ValueError("Publication image is missing from the package")
    if draft:
        files["DRAFT-NOT-FOR-SUBMISSION.txt"] = (
            b"No live OAuth, publisher approval or mobile verification is implied. See docs/hosted.md.\n"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    write_archive(output, files)
    return output


def write_archive(output, files):
    """Write allowlisted entries deterministically to a path or an already-private stream."""
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path, data in sorted(files.items()):
            info = zipfile.ZipInfo(path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("build/freeagent-ai.zip"))
    parser.add_argument("--metadata", type=Path)
    args = parser.parse_args()
    metadata = json.loads(args.metadata.read_text()) if args.metadata else None
    root = Path(__file__).resolve().parent.parent
    print(build(root, args.output, draft=args.draft, metadata=metadata))


if __name__ == "__main__":
    main()
