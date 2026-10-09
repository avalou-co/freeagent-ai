"""MCP server exposing the FreeAgent client as typed tools.

Run over stdio for Claude Code or Codex (`freeagent-ai mcp`), or over
streamable HTTP for ChatGPT (`freeagent-ai mcp --http`). Needs the `mcp` extra.
"""

import base64
import json
import mimetypes
import urllib.error
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlencode, urlsplit

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from .client import BASE, call
from .mcp_auth import BearerAuth, load_token

INSTRUCTIONS = """Generic FreeAgent API tools. Business IDs, rates and rules come from the user's own instructions; ask if missing, never guess.
Rules: reads are free. Before any write call, show the plan and get a clear yes, unless the user gave exact details and said to proceed.
Never touch entries you did not create in this task. After every write, read back with freeagent_get and report what FreeAgent holds, not what you sent. FreeAgent validates accounting rules and resource relationships.
Pass resources as full URLs (e.g. https://api.freeagent.com/v2/projects/123) as returned by freeagent_get."""

mcp = MCPServer("freeagent-ai", instructions=INSTRUCTIONS)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)
API_WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True)


def _path(ref):
    """Accept a /v2/-relative path or a full FreeAgent URL; reject anything else."""
    path = ref[len(BASE) :] if ref.startswith(BASE) else ref
    parsed = urlsplit(path)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path
        or parsed.path.startswith("/")
        or parsed.fragment
        or ".." in unquote(parsed.path).split("/")
    ):
        raise ValueError(f"not a FreeAgent API path: {ref}")
    return path


def _attachment(path):
    """Encode a local file; FreeAgent decides which attachments it accepts."""
    file = Path(path)
    kind = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
    return {"file_name": file.name, "content_type": kind, "data": base64.b64encode(file.read_bytes()).decode()}


@mcp.tool(annotations=READ)
def freeagent_get(path: str, paginate: bool = True) -> Any:
    """GET any FreeAgent API resource. `path` is relative to /v2/ (e.g. 'users/me',
    'projects?view=active', 'timeslips?from_date=2026-01-05&to_date=2026-01-11&per_page=100')
    or a full resource URL. Lists include all pages by default; set `paginate=False`
    to fetch only the requested page. GET rate limits use bounded Retry-After retries."""
    return _api_call("GET", path, paginate=paginate)


@mcp.tool(annotations=READ)
def find_contacts(query: str) -> list:
    """List contacts whose organisation, name or email contains `query` (case-insensitive).
    Use before create_contact to avoid duplicates, and to get the contact URL for invoicing."""
    q = query.lower()
    batch = _api_call("GET", "contacts?view=all&per_page=100")["contacts"]
    fields = ("organisation_name", "first_name", "last_name", "email")
    return [c for c in batch if any(q in (c.get(f) or "").lower() for f in fields)]


@mcp.tool(annotations=WRITE)
def create_contact(
    organisation_name: str = "",
    first_name: str = "",
    last_name: str = "",
    email: str = "",
    address1: str = "",
    town: str = "",
    postcode: str = "",
    country: str = "",
    payment_terms_in_days: int | None = None,
) -> dict:
    """Create one contact and return it as FreeAgent holds it. Needs an organisation name or
    both first and last name, as validated by FreeAgent. Omitted payment terms use
    FreeAgent defaults; explicit zero is forwarded. Run find_contacts first to avoid duplicates."""
    fields = {
        "organisation_name": organisation_name,
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "address1": address1,
        "town": town,
        "postcode": postcode,
        "country": country,
    }
    contact: dict = {k: v for k, v in fields.items() if v}
    if payment_terms_in_days is not None:
        contact["default_payment_terms_in_days"] = payment_terms_in_days
    created = _api_call("POST", "contacts", {"contact": contact})["contact"]
    return _api_call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_timeslip(user: str, project: str, task: str, dated_on: str, hours: str, comment: str = "") -> dict:
    """Create one timeslip and return it as FreeAgent holds it. `user`, `project`, `task`
    are resource URLs; `dated_on` is YYYY-MM-DD; `hours` a decimal string (e.g. '7.5').
    Check for an existing timeslip on that date first."""
    slip = {"user": user, "project": project, "task": task, "dated_on": dated_on, "hours": hours}
    if comment:
        slip["comment"] = comment
    created = _api_call("POST", "timeslips", {"timeslip": slip})["timeslip"]
    return _api_call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_draft_invoice(
    contact: str,
    project: str,
    dated_on: str,
    payment_terms_in_days: int,
    reference: str = "",
    bank_account: str = "",
    include_timeslips: bool = True,
) -> dict:
    """Create a Draft invoice with all automatic emails off, and return it as FreeAgent holds it.
    With `include_timeslips`, the project's unbilled timeslips become the lines (no placeholder
    items are added). Copy reference style, terms and bank account from the project's latest invoice."""
    inv = {
        "contact": contact,
        "project": project,
        "dated_on": dated_on,
        "payment_terms_in_days": payment_terms_in_days,
        "send_new_invoice_emails": False,
        "send_reminder_emails": False,
        "send_thank_you_emails": False,
    }
    if reference:
        inv["reference"] = reference
    if bank_account:
        inv["bank_account"] = bank_account
    if include_timeslips:
        inv["include_timeslips"] = "billed_grouped_by_timeslip"
    created = _api_call("POST", "invoices", {"invoice": inv})["invoice"]
    return _api_call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_expense(
    user: str,
    category: str,
    dated_on: str,
    gross_value: str,
    description: str,
    sales_tax_rate: str = "",
    receipt_path: str = "",
) -> dict:
    """Create one expense claim and return it as FreeAgent holds it. `user` and `category` are
    resource URLs (list categories with freeagent_get 'categories'); `dated_on` is YYYY-MM-DD;
    `gross_value` is the total including VAT as a decimal string, negative for money spent
    (e.g. '-12.50'; check the sign against an existing expense); `sales_tax_rate` e.g. '20.0'.
    `receipt_path` is an optional local file to attach. Check for an existing
    expense on that date first."""
    exp: dict = {
        "user": user,
        "category": category,
        "dated_on": dated_on,
        "gross_value": gross_value,
        "description": description,
    }
    if sales_tax_rate:
        exp["sales_tax_rate"] = sales_tax_rate
    if receipt_path:
        exp["attachment"] = _attachment(receipt_path)
    created = _api_call("POST", "expenses", {"expense": exp})["expense"]
    return _api_call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_project(
    contact: str,
    name: str,
    currency: str,
    normal_billing_rate: str,
    billing_period: str = "day",
    budget: str = "",
    budget_units: str = "Days",
) -> dict:
    """Create an Active project for a contact and return it as FreeAgent holds it. `contact` is a
    resource URL; `normal_billing_rate` a decimal string; `billing_period` 'hour' or 'day';
    `budget_units` 'Hours', 'Days' or 'Monetary' (only used with `budget`). To find the
    contact's existing projects first, use freeagent_get 'projects?contact=<url>&view=active'."""
    project = {
        "contact": contact,
        "name": name,
        "status": "Active",
        "currency": currency,
        "normal_billing_rate": normal_billing_rate,
        "billing_period": billing_period,
    }
    if budget:
        project.update(budget=budget, budget_units=budget_units)
    created = _api_call("POST", "projects", {"project": project})["project"]
    return _api_call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_task(project: str, name: str, billing_rate: str, billing_period: str = "day") -> dict:
    """Create an Active task on a project and return it as FreeAgent holds it. `project` is a
    resource URL; `billing_rate` a decimal string; `billing_period` 'hour' or 'day'. To list the
    project's tasks first, use freeagent_get 'tasks?project=<url>&view=active'."""
    task = {"name": name, "status": "Active", "billing_rate": billing_rate, "billing_period": billing_period}
    created = _api_call("POST", "tasks?" + urlencode({"project": project}), {"task": task})["task"]
    return _api_call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_draft_estimate(
    contact: str,
    dated_on: str,
    items: list[dict],
    project: str = "",
    reference: str = "",
    currency: str = "",
) -> dict:
    """Create a Draft estimate (never sent) and return it as FreeAgent holds it. `contact` and
    `project` are resource URLs; `items` are lines like {"description": "Design", "item_type": "Days",
    "quantity": "2", "price": "400"}. Currency defaults to FreeAgent's; copy reference style and currency from the contact's latest estimate."""
    est = {"contact": contact, "dated_on": dated_on, "status": "Draft", "estimate_items": items}
    if project:
        est["project"] = project
    if currency:
        est["currency"] = currency
    if reference:
        est["reference"] = reference
    created = _api_call("POST", "estimates", {"estimate": est})["estimate"]
    return _api_call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_bill(
    contact: str,
    reference: str,
    dated_on: str,
    due_on: str,
    items: list[dict],
    attachment_path: str = "",
) -> dict:
    """Create one supplier bill and return it as FreeAgent holds it. `contact` is the supplier's
    resource URL; `dated_on` and `due_on` are YYYY-MM-DD. `items` are lines, each
    {"category": <category URL>, "description": str, "total_value": "120.00", "sales_tax_rate": "20.0"}
    (`total_value` includes taxes; use `total_value_ex_tax` for net amounts; `sales_tax_rate` optional; list categories with
    freeagent_get 'categories'). `attachment_path` is an optional local file to attach.
    Check for an existing bill with that reference first (freeagent_get 'bills?view=open'
    lists unpaid bills, 'bills?view=overdue' overdue ones)."""
    bill: dict = {
        "contact": contact,
        "reference": reference,
        "dated_on": dated_on,
        "due_on": due_on,
        "bill_items": items,
    }
    if attachment_path:
        bill["attachment"] = _attachment(attachment_path)
    created = _api_call("POST", "bills", {"bill": bill})["bill"]
    return _api_call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def explain_bank_transaction(
    bank_transaction: str,
    dated_on: str,
    gross_value: str,
    category: str = "",
    paid_invoice: str = "",
    paid_bill: str = "",
    description: str = "",
) -> dict:
    """Create one explanation for a bank transaction and return it as FreeAgent holds it.
    `bank_transaction` and exactly one of `category`, `paid_invoice`, `paid_bill` are resource
    URLs; `dated_on` is YYYY-MM-DD; `gross_value` a decimal string with the transaction's sign
    (e.g. '-12.50'). Find candidates with freeagent_get 'bank_transactions?bank_account=<url>&view=unexplained'.
    Needs a clear yes per transaction."""
    targets = {"category": category, "paid_invoice": paid_invoice, "paid_bill": paid_bill}
    chosen = {k: v for k, v in targets.items() if v}
    exp = {"bank_transaction": bank_transaction, "dated_on": dated_on, "gross_value": gross_value, **chosen}
    if description:
        exp["description"] = description
    created = _api_call("POST", "bank_transaction_explanations", {"bank_transaction_explanation": exp})
    return _api_call("GET", _path(created["bank_transaction_explanation"]["url"]))


def _api_call(method, path, body=None, **kwargs):
    """Expose API status and validation errors without exposing authentication responses."""
    try:
        return call(method, _path(path), body, **kwargs)
    except urllib.error.HTTPError as error:
        detail = ""
        if error.code in {400, 409, 422}:
            try:
                response = json.loads(error.read(8192))
                if isinstance(response, dict) and "errors" in response:
                    detail = ": " + json.dumps(response["errors"])
            except (ValueError, AttributeError):
                pass
        raise ToolError(f"FreeAgent HTTP {error.code}{detail}") from error


def _write(method, path, confirmed, body=None):
    if confirmed is not True:
        raise ToolError("Show the write plan and obtain user confirmation first")
    return _api_call(method, path, body)


@mcp.tool(annotations=API_WRITE)
def freeagent_post(path: str, body: dict, confirmed: bool) -> Any:
    """POST the exact JSON body to a FreeAgent API path or resource URL after user approval.
    FreeAgent validates the payload. Returns its response or empty-response HTTP status.
    Read back using freeagent_get. Inspect uncertain outcomes before any retry."""
    return _write("POST", path, confirmed, body)


@mcp.tool(annotations=API_WRITE)
def freeagent_put(path: str, body: dict, confirmed: bool) -> Any:
    """PUT the exact JSON body to a FreeAgent API path or resource URL after user approval.
    Only modify entries created during the current user request, per agent rules.
    FreeAgent validates the payload. Returns its response or empty-response HTTP status.
    Read back using freeagent_get. Inspect uncertain outcomes before any retry."""
    return _write("PUT", path, confirmed, body)


@mcp.tool(annotations=API_WRITE)
def freeagent_delete(path: str, confirmed: bool) -> Any:
    """DELETE a FreeAgent API path or resource URL after user approval. Only delete entries
    created during the current user request, per agent rules. FreeAgent validates the operation.
    Returns its response or empty-response HTTP status; this alone does not verify absence.
    Read back the resource or its parent using freeagent_get. Inspect uncertain outcomes before retrying."""
    return _write("DELETE", path, confirmed)


def run(http=False, host="127.0.0.1", port=8000):
    """Serve over stdio, or streamable HTTP behind bearer-token auth (FREEAGENT_MCP_TOKEN required)."""
    if not http:
        mcp.run()
        return
    import anyio
    import uvicorn

    token = load_token()  # raises before binding anything if unset or weak
    app = BearerAuth(mcp.streamable_http_app(host=host), token)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    anyio.run(server.serve)
