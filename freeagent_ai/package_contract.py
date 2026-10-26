"""API-only marketplace workflow contracts, not accounting validation.

Static contracts and synthetic HTTP evidence cannot establish assistant behavior or
actual marketplace web/iOS installation. No calculation engine belongs here.
"""

import hashlib
import json
import posixpath
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .public_tools import CORRECTIONS, CREATES, REGISTRY, RESOURCES, TAX_RETURNS

# Explicit reviewed entry points, plus every operation referenced by the actual
# workflow (not the full registry appendix). This is a product contract, not a
# parallel task/status tracker. New skills must declare their executable path.
SKILLS = {
    "bank-reconcile": ("list_bank_transactions", "explain_bank_transaction"),
    "bills": ("list_bills", "create_bill"),
    "cash-flow": ("list_bank_accounts", "list_invoices", "list_bills"),
    "clients": ("list_contacts", "create_contact", "create_project", "create_task"),
    "credit-notes": ("create_draft_credit_note", "create_credit_note_reconciliation"),
    "estimates": ("list_estimates", "create_draft_estimate"),
    "expenses": ("list_expenses", "create_expense_from_payload"),
    "invoice-status": ("list_invoices", "get_invoice"),
    "invoicing": ("list_invoices", "create_draft_invoice_from_payload"),
    "mileage": ("get_mileage_settings", "create_mileage_expense"),
    "profitability": ("list_projects", "list_timeslips", "list_invoices"),
    "receipts": ("list_expenses", "list_bills", "create_expense_from_payload", "create_bill"),
    "recurring-revenue": ("list_recurring_invoices", "get_recurring_invoice"),
    "reports": ("get_profit_and_loss", "get_balance_sheet", "get_trial_balance"),
    "tax-overview": ("list_vat_returns", "list_corporation_tax_returns", "list_self_assessment_returns"),
    "timesheets": ("list_timeslips", "create_timeslip"),
}
TOOL_TOKEN = re.compile(
    r"\b((?:list|get|create|update|delete|explain|add|remove|find|calculate|execute|run)_[a-z][a-z0-9_]*)\b"
)
CALL_REFERENCE = re.compile(r"\b(?:call|invoke|tool|helper|function)\s+`([a-z][a-z0-9_]*)(?:\(|`)", re.I)
LINK = re.compile(r"\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)")
LOCAL_IMPORT = re.compile(r"\b(?:freeagent_ai\.(?:analysis|recurring)|runpy|preview\.py)\b")
GENERIC = re.compile(r"\bfreeagent_(?:get|post|put|delete)\b")
LOCAL_COMMAND = re.compile(
    r"(?:^|[.;:]\s*)(?:run|execute|invoke|import|from)\s+[^\n]*(?:python|script|runner|calculator|freeagent_ai|shell|terminal)"
    r"|\b(?:python[0-9.]*\s+(?:-m\s+|[\w./-]+\.py)|(?:pip|uvx|bash|run_code|execute_code)\s+)"
    r"|\b(?:use|requires?|needs?|open|read|write)\s+(?:an?\s+|the\s+)?(?:available\s+|client[- ]|local\s+|code\s+)?"
    r"(?:python|code runner|calculator|shell|terminal|filesystem|local file|local path)\b",
    re.I,
)
NEGATIVE = re.compile(r"\b(?:no|not|never|without|prohibit\w*|doesn't|cannot)\b", re.I)
API_COMMAND = re.compile(
    r"\b(?:GET|POST|PUT|DELETE)\s+(?:invoices|expenses|bills|contacts|timeslips|projects|tasks|categories|users|estimates|bank_[a-z_]+)(?:\b|/|\?)"
)
ACCOUNTING_INSTRUCTION = re.compile(
    r"^\s*(?:(?:\d+\.|[-*])\s+)?(?:(?:then|also|next)\s+)?(?:calculate|compute|derive|expand|convert|clamp|sum|forecast)\b.{0,65}"
    r"\b(?:future|forecasts?|cash|tax|vat|margins?|profit|budget|mileage|rates?|thresholds?|amounts?|balances?|exchange|recurrence|billing|commitments?)\b",
    re.I,
)
FILE_OUTPUT = re.compile(r"\b(?:return|deliver|download|save)\b.{0,70}\b(?:pdf|file|document|base64)\b", re.I)
LOCAL_PATH = re.compile(r"(?:/private/tmp/|/tmp/|/Users/|[A-Z]:\\)")
FORBIDDEN_TOOLS = re.compile(r"(?:^calculate_|forecast|profitability|margin|budget_remaining|mileage_preview)")


def workflow(text):
    """Listing every tool in an appendix is not evidence of workflow coverage."""
    return text.split("## Hosted transport", 1)[0]


def tool_names(text):
    return set(TOOL_TOKEN.findall(text)) | set(CALL_REFERENCE.findall(text))


def _headings(text):
    counts, anchors = {}, set()
    for title in re.findall(r"^#{1,6}\s+(.+)$", text, re.M):
        slug = re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        anchors.add(slug + (f"-{count}" if count else ""))
    return anchors


def validate_links(files):
    for path, data in files.items():
        if not path.endswith(".md"):
            continue
        for raw in LINK.findall(data.decode()):
            parsed = urlsplit(raw)
            if parsed.scheme in {"https", "http", "mailto"}:
                continue
            if parsed.scheme or parsed.netloc:
                raise ValueError(f"Unsupported packaged link: {path} -> {raw}")
            target = (
                posixpath.normpath(posixpath.join(posixpath.dirname(path), unquote(parsed.path)))
                if parsed.path
                else path
            )
            if target not in files or target.startswith("../"):
                raise ValueError(f"Missing packaged reference: {path} -> {raw}")
            if (
                parsed.fragment
                and target.endswith(".md")
                and unquote(parsed.fragment) not in _headings(files[target].decode())
            ):
                raise ValueError(f"Missing packaged anchor: {path} -> {raw}")


def validate_operations():
    """Bind descriptors to supported API routes, never an arbitrary local handler.

    Endpoint inventory changes still need provider-contract review; this structural
    check does not attempt to infer accounting rules from implementation code.
    """
    routes = {("GET", endpoint) for endpoint in RESOURCES}
    routes.update(("GET", endpoint + "/{id}") for endpoint in RESOURCES)
    routes.update(("GET", endpoint) for endpoint in TAX_RETURNS)
    routes.update(("GET", endpoint + "/{period_ends_on}") for endpoint in TAX_RETURNS)
    routes.update(
        ("GET", endpoint)
        for endpoint in [
            "company",
            "users/me",
            "expenses/mileage_settings",
            "bank_transaction_explanations/{id}",
            "accounting/profit_and_loss/summary",
            "accounting/balance_sheet",
            "accounting/trial_balance/summary",
        ]
    )
    for endpoint, (_, update, delete) in CORRECTIONS.items():
        if update:
            routes.add(("PUT", endpoint + "/{id}"))
        if delete:
            routes.add(("DELETE", endpoint + "/{id}"))
    routes.update((method, "bank_transaction_explanations/{id}/attachments") for method in ["GET", "POST", "PUT"])
    for name, op in REGISTRY.items():
        create = op.method == "POST" and op.helper in CREATES
        if (
            not isinstance(op.endpoint, str)
            or not op.endpoint
            or FORBIDDEN_TOOLS.search(name)
            or FORBIDDEN_TOOLS.search(op.helper)
            or (not create and (op.method, op.endpoint) not in routes)
            or (create and op.root != CREATES[op.helper])
        ):
            raise ValueError(f"Non-provider operation in hosted inventory: {name}")
        if op.method != "GET":
            schema = op.descriptor.input_schema
            if (
                "confirmed" not in schema.get("required", [])
                or schema.get("properties", {}).get("confirmed", {}).get("type") != "boolean"
            ):
                raise ValueError(f"Write operation lacks explicit approval input: {name}")
        if create:
            expected = next(
                endpoint for endpoint, (root, *_) in {**CORRECTIONS, **RESOURCES}.items() if root == op.root
            )
            if op.endpoint != expected or op.helper != name:
                raise ValueError(f"Non-provider operation in hosted inventory: {name}")


def validate_workflow(path, text):
    body = workflow(text)
    for name in tool_names(body):
        if name not in REGISTRY:
            raise ValueError(f"Unresolved packaged tool reference: {name} ({path})")
    if GENERIC.search(body):
        raise ValueError(f"Local generic executor leaked into hosted package: {path}")
    if LOCAL_IMPORT.search(body):
        raise ValueError(f"Retired local calculation instruction: {path}")
    if re.search(r"^\s*```(?:python|py|bash|sh|shell)\b", body, re.M):
        raise ValueError(f"Client runtime code block in workflow: {path}")
    # Join Markdown continuations before evaluating instructions: a prohibition
    # must not become an apparent command merely because prose wraps at 80 cols.
    prose = re.sub(r"(?<!\n)\n(?!\n)", " ", body)
    for clause in re.split(r"[.;]\s+|\n\s*\n", prose):
        if API_COMMAND.search(clause):
            raise ValueError(f"API executor instruction instead of named tool: {path}")
        if NEGATIVE.search(clause):
            continue
        if LOCAL_COMMAND.search(clause):
            raise ValueError(f"Required client runtime in workflow: {path}")
        if ACCOUNTING_INSTRUCTION.search(clause):
            raise ValueError(f"Custom accounting instruction in workflow: {path}")
        if FILE_OUTPUT.search(clause) or LOCAL_PATH.search(clause):
            raise ValueError(f"Unsupported file-output or local-path promise: {path}")
    return tool_names(body)


def coverage(files):
    present = {p.split("/")[1] for p in files if re.fullmatch(r"skills/[^/]+/SKILL.md", p)}
    if present != set(SKILLS):
        raise ValueError("Packaged skills differ from the reviewed capability contracts")
    result = {}
    for skill, required in SKILLS.items():
        path = f"skills/{skill}/SKILL.md"
        text = files[path].decode()
        names = validate_workflow(path, text)
        absent = set(required) - names
        if absent:
            raise ValueError(f"Missing required workflow operations: {skill}: {sorted(absent)}")
        operations, artifacts = [], []
        for name in sorted(names):
            op = REGISTRY[name]
            metadata = op.descriptor.model_dump(by_alias=True).get("_meta") or {}
            for parameter in metadata.get("openai/fileParams", []):
                artifacts.append(
                    {
                        "tool": name,
                        "parameter": parameter,
                        "input_schema": op.descriptor.input_schema["properties"][parameter],
                        "transport": "ChatGPT file reference; bounded hosted download",
                    }
                )
            operations.append(
                {
                    "name": name,
                    "method": op.method,
                    "endpoint": op.endpoint,
                    "input_schema": op.descriptor.input_schema,
                    "output_schema": op.descriptor.output_schema,
                    "approval_parameter": "confirmed" if op.method != "GET" else None,
                    "result": "provider JSON with source references; errors are explicit",
                }
            )
        result[skill] = {
            "workflow_sha256": hashlib.sha256(files[path]).hexdigest(),
            "required_operations": list(required),
            "operations": operations,
            "linked_evidence": sorted(LINK.findall(workflow(text))),
            "input_artifacts": artifacts,
            "output_artifacts": ["provider JSON / assistant explanation"],
            "verification_limits": "Static contract and synthetic HTTP fixtures do not prove assistant decisions or live web/iOS installation.",
        }
    return result


def validate_contract(files, *, root=None):
    validate_operations()
    for path in files:
        if path.endswith((".py", ".pyc", ".sh", ".ipynb", ".js")):
            raise ValueError(f"Executable client helper in hosted package: {path}")
    validate_links(files)
    result = coverage(files)
    if root is not None:
        root = Path(root)
        retired = [root / "freeagent_ai" / f"{name}.py" for name in ["analysis", "recurring"]]
        retired.append(root / ".agents/skills/mileage/scripts/preview.py")
        if any(p.exists() for p in retired):
            raise ValueError("Retired accounting engine exists in release source")
        sources = json.loads(files["docs/source-digests.json"])
        expected = {str(p.relative_to(root)) for p in (root / ".agents/skills").glob("*/SKILL.md")}
        expected.update(
            p for p in files if p.startswith("docs/") and p.endswith(".md") and p != "docs/receipt-review-cases.md"
        )
        expected.add("publication/receipt-review-cases.md")
        if set(sources) != expected:
            raise ValueError("Canonical source digest coverage is incomplete")
        for path, digest in sources.items():
            source = root / path
            if source.is_symlink() or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != digest:
                raise ValueError(f"Canonical source digest mismatch: {path}")

    return result


def main():
    """Build and validate the exact draft contents without bypassing release gates."""
    from .public_package import package_files

    root = Path(__file__).resolve().parents[1]
    files = package_files(root)
    print(f"Validated {len(SKILLS)} packaged skills and {len(REGISTRY)} provider-backed remote operations")
    if "docs/capabilities.json" not in files:
        raise ValueError("Capability contract is missing")


if __name__ == "__main__":
    main()
