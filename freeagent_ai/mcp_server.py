"""MCP server exposing the FreeAgent client as typed tools.

Run over stdio for Claude Code or Codex (`freeagent-ai mcp`), or over
streamable HTTP for ChatGPT (`freeagent-ai mcp --http`). Needs the `mcp` extra.
"""

import base64
import mimetypes
from pathlib import Path
from typing import Literal

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from . import corrections
from .client import BASE, call
from .mcp_auth import BearerAuth, load_token

INSTRUCTIONS = """Generic FreeAgent API tools. Business IDs, rates and rules come from the user's own instructions; ask if missing, never guess.
Rules: reads are free. Call begin_task at the start of each user task, pass its task_id to create/correction tools, and finish_task when done. Pass previous_task_id when starting the next task. Before any create_*, update_* or delete_* call, show the plan and get a clear yes, unless the user gave exact details and said to proceed.
Never touch entries you did not create in this task. Report what FreeAgent holds (the tools read back for you), not what you sent.
Pass resources as full URLs (e.g. https://api.freeagent.com/v2/projects/123) as returned by freeagent_get."""

mcp = MCPServer("freeagent-ai", instructions=INSTRUCTIONS)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)
CorrectionResource = Literal["timeslip", "invoice", "estimate", "expense", "bill"]
LOCAL_STATE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
CORRECTION = ToolAnnotations(read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=True)
RECEIPT_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/gif"}


def _path(ref):
    """Accept a /v2/-relative path or a full FreeAgent URL; reject anything else."""
    path = ref[len(BASE) :] if ref.startswith(BASE) else ref
    if "://" in path or path.startswith("/") or ".." in path:
        raise ValueError(f"not a FreeAgent API path: {ref}")
    return path


def _attachment(path):
    """Encode a local PDF/PNG/JPG/GIF file as a FreeAgent attachment."""
    file = Path(path)
    kind = mimetypes.guess_type(file.name)[0]
    if kind not in RECEIPT_TYPES:
        raise ValueError(f"attachment must be PDF, PNG, JPG or GIF: {path}")
    return {"file_name": file.name, "content_type": kind, "data": base64.b64encode(file.read_bytes()).decode()}


@mcp.tool(annotations=READ)
def freeagent_get(path: str, paginate: bool = True) -> dict:
    """GET any FreeAgent API resource. `path` is relative to /v2/ (e.g. 'users/me',
    'projects?view=active', 'timeslips?from_date=2026-01-05&to_date=2026-01-11&per_page=100')
    or a full resource URL. Lists include all pages by default; set `paginate=False`
    to fetch only the requested page. GET rate limits use bounded Retry-After retries."""
    return call("GET", _path(path), paginate=paginate)


@mcp.tool(annotations=READ)
def find_contacts(query: str) -> list:
    """List contacts whose organisation, name or email contains `query` (case-insensitive).
    Use before create_contact to avoid duplicates, and to get the contact URL for invoicing."""
    q = query.lower()
    batch = call("GET", "contacts?view=all&per_page=100")["contacts"]
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
    payment_terms_in_days: int = 0,
) -> dict:
    """Create one contact and return it as FreeAgent holds it. Needs an organisation name or
    both first and last name. Run find_contacts first to avoid duplicates."""
    if not (organisation_name or (first_name and last_name)):
        raise ValueError("give organisation_name, or both first_name and last_name")
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
    if payment_terms_in_days:
        contact["default_payment_terms_in_days"] = payment_terms_in_days
    created = call("POST", "contacts", {"contact": contact})["contact"]
    return call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_timeslip(
    user: str, project: str, task: str, dated_on: str, hours: str, comment: str = "", task_id: str = ""
) -> dict:
    """Create one timeslip and return it as FreeAgent holds it. `user`, `project`, `task`
    are resource URLs; `dated_on` is YYYY-MM-DD; `hours` a decimal string (e.g. '7.5').
    Check for an existing timeslip on that date first."""
    slip = {"user": user, "project": project, "task": task, "dated_on": dated_on, "hours": hours}
    if comment:
        slip["comment"] = comment
    return corrections.create(task_id, "timeslip", "timeslips", {"timeslip": slip}, call, BASE)


@mcp.tool(annotations=WRITE)
def create_draft_invoice(
    contact: str,
    project: str,
    dated_on: str,
    payment_terms_in_days: int,
    reference: str = "",
    bank_account: str = "",
    include_timeslips: bool = True,
    task_id: str = "",
) -> dict:
    """Create a Draft invoice with all automatic emails off, and return it as FreeAgent holds it.
    With `include_timeslips`, the project's unbilled timeslips become the lines (no placeholder
    items are added). Copy reference style, terms and bank account from the project's latest invoice."""
    inv = {
        "contact": contact,
        "project": project,
        "dated_on": dated_on,
        "payment_terms_in_days": payment_terms_in_days,
        **corrections.INVOICE_EMAILS_OFF,
    }
    if reference:
        inv["reference"] = reference
    if bank_account:
        inv["bank_account"] = bank_account
    if include_timeslips:
        inv["include_timeslips"] = "billed_grouped_by_timeslip"
    return corrections.create(task_id, "invoice", "invoices", {"invoice": inv}, call, BASE)


@mcp.tool(annotations=WRITE)
def create_expense(
    user: str,
    category: str,
    dated_on: str,
    gross_value: str,
    description: str,
    sales_tax_rate: str = "",
    receipt_path: str = "",
    task_id: str = "",
) -> dict:
    """Create one expense claim and return it as FreeAgent holds it. `user` and `category` are
    resource URLs (list categories with freeagent_get 'categories'); `dated_on` is YYYY-MM-DD;
    `gross_value` is the total including VAT as a decimal string, negative for money spent
    (e.g. '-12.50'; check the sign against an existing expense); `sales_tax_rate` e.g. '20.0'.
    `receipt_path` is an optional local PDF/PNG/JPG/GIF file to attach. Check for an existing
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
    return corrections.create(task_id, "expense", "expenses", {"expense": exp}, call, BASE)


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
    created = call("POST", "projects", {"project": project})["project"]
    return call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_task(project: str, name: str, billing_rate: str, billing_period: str = "day") -> dict:
    """Create an Active task on a project and return it as FreeAgent holds it. `project` is a
    resource URL; `billing_rate` a decimal string; `billing_period` 'hour' or 'day'. To list the
    project's tasks first, use freeagent_get 'tasks?project=<url>&view=active'."""
    task = {"name": name, "status": "Active", "billing_rate": billing_rate, "billing_period": billing_period}
    created = call("POST", f"tasks?project={project}", {"task": task})["task"]
    return call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_draft_estimate(
    contact: str,
    dated_on: str,
    items: list[dict],
    project: str = "",
    reference: str = "",
    currency: str = "",
    task_id: str = "",
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
    return corrections.create(task_id, "estimate", "estimates", {"estimate": est}, call, BASE)


@mcp.tool(annotations=WRITE)
def create_bill(
    contact: str,
    reference: str,
    dated_on: str,
    due_on: str,
    items: list[dict],
    attachment_path: str = "",
    task_id: str = "",
) -> dict:
    """Create one supplier bill and return it as FreeAgent holds it. `contact` is the supplier's
    resource URL; `dated_on` and `due_on` are YYYY-MM-DD. `items` are lines, each
    {"category": <category URL>, "description": str, "total_value": "120.00", "sales_tax_rate": "20.0"}
    (`total_value` includes taxes; use `total_value_ex_tax` for net amounts; `sales_tax_rate` optional; list categories with
    freeagent_get 'categories'). `attachment_path` is an optional local PDF/PNG/JPG/GIF file to attach.
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
    return corrections.create(task_id, "bill", "bills", {"bill": bill}, call, BASE)


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
    if len(chosen) != 1:
        raise ValueError("give exactly one of category, paid_invoice, paid_bill")
    exp = {"bank_transaction": bank_transaction, "dated_on": dated_on, "gross_value": gross_value, **chosen}
    if description:
        exp["description"] = description
    created = call("POST", "bank_transaction_explanations", {"bank_transaction_explanation": exp})
    return call("GET", _path(created["bank_transaction_explanation"]["url"]))


@mcp.tool(annotations=LOCAL_STATE)
def begin_task(previous_task_id: str = "") -> dict:
    """Start a user task and return an opaque task_id valid for one hour. Pass that handle
    to create and correction tools. When starting the next task, pass previous_task_id
    to revoke the old handle. Never reuse a handle from another user task."""
    return corrections.begin(previous_task_id)


@mcp.tool(annotations=LOCAL_STATE)
def finish_task(task_id: str) -> dict:
    """Close a completed user task, discarding its correction rights. No FreeAgent writes."""
    return corrections.finish(task_id)


@mcp.tool(annotations=CORRECTION)
def update_created_entry(
    resource_type: CorrectionResource, resource: str, changes: dict, confirmed: bool, task_id: str
) -> dict:
    """Correct an entry created with this task_id after showing the changes and
    getting a clear yes (confirmed=True). Types: timeslip, invoice, estimate, expense, bill.
    Only Draft invoices/estimates, unbilled stopped timeslips, unrebilled expenses and wholly
    unpaid/unrebilled bills. Refuses external changes. Returns FreeAgent's readback.
    Fields: timeslip dated_on/hours/comment; invoice dated_on/payment_terms_in_days/reference/
    comments/invoice_items; estimate dated_on/reference/notes/estimate_items; expense dated_on/
    gross_value/description/sales_tax_rate; bill reference/dated_on/due_on/comments/bill_items.
    Invoice/estimate lines: id (existing line only), description/item_type/quantity/price/sales_tax_rate;
    omit id to add a new line. Bill lines: existing url, description/total_value/total_value_ex_tax/
    sales_tax_rate. No status, relationship, attachment or line-deletion changes.
    Never retries an uncertain write; task must still be live."""
    return corrections.correct(task_id, resource_type, resource, confirmed, changes, call, BASE)


@mcp.tool(annotations=CORRECTION)
def delete_created_entry(resource_type: CorrectionResource, resource: str, confirmed: bool, task_id: str) -> dict:
    """Delete an eligible entry created with this task_id only after a clear yes
    to the exact deletion plan (confirmed=True). Same restrictions as update_created_entry.
    Verifies deletion with GET returning 404. Unknown outcomes require manual reconciliation."""
    return corrections.correct(task_id, resource_type, resource, confirmed, None, call, BASE)


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
