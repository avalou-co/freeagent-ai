"""Status checks, field validation and readback for FreeAgent corrections."""

import copy
import re
import urllib.error
from decimal import Decimal, InvalidOperation

from mcp.server.mcpserver.exceptions import ToolError


class CorrectionError(ValueError, ToolError):
    """An actionable safety refusal that MCP can expose without a traceback."""


FIELDS = {
    "timeslip": {"dated_on", "hours", "comment"},
    "invoice": {"dated_on", "payment_terms_in_days", "reference", "comments", "invoice_items"},
    "estimate": {"dated_on", "reference", "notes", "estimate_items"},
    "expense": {"dated_on", "gross_value", "description", "sales_tax_rate"},
    "bill": {"reference", "dated_on", "due_on", "comments", "bill_items"},
}
COLLECTIONS = {kind: kind + "s" for kind in FIELDS}
INVOICE_EMAILS_OFF = dict.fromkeys(("send_new_invoice_emails", "send_reminder_emails", "send_thank_you_emails"), False)
TIME_LINE_FIELDS = frozenset({"id", "description", "item_type", "quantity", "price", "sales_tax_rate"})
LINE_FIELDS = {
    "invoice": TIME_LINE_FIELDS,
    "estimate": TIME_LINE_FIELDS,
    "bill": frozenset({"url", "description", "total_value", "total_value_ex_tax", "sales_tax_rate"}),
}


def _resource(kind, ref, base):
    if kind not in COLLECTIONS:
        raise CorrectionError("Unsupported correction resource")
    path = ref[len(base) :] if ref.startswith(base) else ref
    if not re.fullmatch(rf"{COLLECTIONS[kind]}/[1-9][0-9]*", path):
        raise CorrectionError("Expected an exact FreeAgent resource URL or collection/id path")
    return path


def _eligible(kind, entry):
    if kind in {"invoice", "estimate"} and entry.get("status") != "Draft":
        raise CorrectionError("Only Draft invoices and estimates may be corrected")
    if kind == "timeslip" and (entry.get("billed_on_invoice") or entry.get("timer")):
        raise CorrectionError("Cannot correct billed timeslips or running timers")
    if kind in {"expense", "bill"} and any(entry.get(k) for k in ("rebilled_on_invoice", "rebilled_on_invoice_item")):
        raise CorrectionError("Cannot correct rebilled expenses or bills")
    if kind == "bill":
        try:
            unpaid = Decimal(str(entry["paid_value"])) == 0
        except (KeyError, InvalidOperation):
            unpaid = False
        if not unpaid or entry.get("status") not in {"Open", "Overdue", "Zero Value"}:
            raise CorrectionError("Only wholly unpaid bills may be corrected")


def _changes(kind, changes, entry):
    if not changes or set(changes) - FIELDS[kind]:
        raise CorrectionError(
            "Empty changes or unsupported fields; status, relationships and email settings cannot be changed"
        )
    items_key = f"{kind}_items"
    if items_key in changes:
        items = changes[items_key]
        if not isinstance(items, list) or not items:
            raise CorrectionError("Line changes must be a nonempty list")
        existing = entry.get(items_key, [])
        for item in items:
            if not isinstance(item, dict) or not item or set(item) - LINE_FIELDS[kind]:
                raise CorrectionError("Unsupported line fields; deletion and relationship changes are forbidden")
            identity = "url" if kind == "bill" else "id"
            if identity in item:
                ids = {str(line.get(identity)) for line in existing if line.get(identity) is not None}
                if identity == "id":
                    ids.update(line["url"].rsplit("/", 1)[-1] for line in existing if line.get("url"))
                if str(item[identity]) not in ids:
                    raise CorrectionError("Line does not belong to this entry")
            elif kind == "bill":
                raise CorrectionError("Bill line corrections require an existing line URL")
    result = copy.deepcopy(changes)
    if kind == "invoice":
        result.update(INVOICE_EMAILS_OFF)
    return result


def correct(kind, ref, confirmed, changes, call, base):
    if confirmed is not True:
        raise CorrectionError("Show the exact correction plan and obtain user confirmation first")
    path = _resource(kind, ref, base)
    entry = call("GET", path)[kind]
    _eligible(kind, entry)
    body = {kind: _changes(kind, changes, entry)} if changes is not None else None
    try:
        if changes is not None:
            assert body is not None
            if kind == "estimate" and "estimate_items" in body[kind]:
                items = body[kind].pop("estimate_items")
                if body[kind]:
                    call("PUT", path, body)
                for item in items:
                    if "id" in item:
                        item_id = item.pop("id")
                        call("PUT", f"estimate_items/{item_id}", {"estimate_item": item})
                    else:
                        call("POST", "estimate_items", {"estimate": base + path, "estimate_item": item})
            else:
                call("PUT", path, body)
            result = call("GET", path)
            _eligible(kind, result[kind])
            return result
        call("DELETE", path)
        try:
            call("GET", path)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return {"deleted": True, "url": base + path}
            raise
        raise CorrectionError("Entry still exists after deletion")
    except Exception as error:
        raise CorrectionError(
            "Correction outcome could not be verified; inspect FreeAgent without retrying or recreating the entry"
        ) from error
