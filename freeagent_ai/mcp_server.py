"""MCP server exposing the FreeAgent client as typed tools.

Run over stdio for Claude Code or Codex (`freeagent-ai mcp`), or over
streamable HTTP for ChatGPT (`freeagent-ai mcp --http`). Needs the `mcp` extra.
"""

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from .client import BASE, call
from .mcp_auth import BearerAuth, load_token

INSTRUCTIONS = """Generic FreeAgent API tools. Business IDs, rates and rules come from the user's own instructions; ask if missing, never guess.
Rules: reads are free. Before any create_* call, show the plan and get a clear yes, unless the user gave exact details and said to proceed.
Never touch entries you did not create in this task. Report what FreeAgent holds (the tools read back for you), not what you sent.
Pass resources as full URLs (e.g. https://api.freeagent.com/v2/projects/123) as returned by freeagent_get."""

mcp = MCPServer("freeagent-ai", instructions=INSTRUCTIONS)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True)


def _path(ref):
    """Accept a /v2/-relative path or a full FreeAgent URL; reject anything else."""
    path = ref[len(BASE) :] if ref.startswith(BASE) else ref
    if "://" in path or path.startswith("/") or ".." in path:
        raise ValueError(f"not a FreeAgent API path: {ref}")
    return path


@mcp.tool(annotations=READ)
def freeagent_get(path: str) -> dict:
    """GET any FreeAgent API resource. `path` is relative to /v2/ (e.g. 'users/me',
    'projects?view=active', 'timeslips?from_date=2026-01-05&to_date=2026-01-11&per_page=100')
    or a full resource URL."""
    return call("GET", _path(path))


@mcp.tool(annotations=WRITE)
def create_timeslip(user: str, project: str, task: str, dated_on: str, hours: str, comment: str = "") -> dict:
    """Create one timeslip and return it as FreeAgent holds it. `user`, `project`, `task`
    are resource URLs; `dated_on` is YYYY-MM-DD; `hours` a decimal string (e.g. '7.5').
    Check for an existing timeslip on that date first."""
    slip = {"user": user, "project": project, "task": task, "dated_on": dated_on, "hours": hours}
    if comment:
        slip["comment"] = comment
    created = call("POST", "timeslips", {"timeslip": slip})["timeslip"]
    return call("GET", _path(created["url"]))


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
    created = call("POST", "invoices", {"invoice": inv})["invoice"]
    return call("GET", _path(created["url"]))


@mcp.tool(annotations=WRITE)
def create_draft_estimate(
    contact: str, dated_on: str, items: list[dict], project: str = "", reference: str = "", currency: str = "GBP"
) -> dict:
    """Create a Draft estimate (never sent) and return it as FreeAgent holds it. `contact` and
    `project` are resource URLs; `items` are lines like {"description": "Design", "item_type": "Days",
    "quantity": "2", "price": "400"}. Copy reference style and currency from the contact's latest estimate."""
    est = {"contact": contact, "dated_on": dated_on, "currency": currency, "status": "Draft", "estimate_items": items}
    if project:
        est["project"] = project
    if reference:
        est["reference"] = reference
    created = call("POST", "estimates", {"estimate": est})["estimate"]
    return call("GET", _path(created["url"]))


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
