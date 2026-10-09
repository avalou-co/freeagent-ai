"""Ephemeral, task-scoped provenance for corrections; never imports credentials."""

import copy
import re
import secrets
import threading
import time
import urllib.error
from decimal import Decimal, InvalidOperation

from mcp.server.mcpserver.exceptions import ToolError


class CorrectionError(ValueError, ToolError):
    """An actionable safety refusal that MCP can expose without a traceback."""


# Task handles are opaque capabilities issued here, never caller-chosen identifiers.
_TASKS: dict = {}
TASK_TTL = 3600
MAX_TASKS = 100
MAX_ENTRIES = 1000
_LOCK = threading.RLock()
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


def begin(previous_task_id=""):
    with _LOCK:
        now = time.monotonic()
        for key, (expires, _) in list(_TASKS.items()):
            if expires <= now:
                del _TASKS[key]
        if previous_task_id:
            _task(previous_task_id)
            del _TASKS[previous_task_id]
        if len(_TASKS) >= MAX_TASKS:
            raise CorrectionError("Too many active tasks; close a task or wait for expiry")
        task_id = secrets.token_urlsafe(32)
        _TASKS[task_id] = (now + TASK_TTL, {})
    return {"task_id": task_id, "expires_in_seconds": TASK_TTL}


def finish(task_id):
    with _LOCK:
        _task(task_id)
        del _TASKS[task_id]
    return {"task_closed": True}


def _task(task_id):
    if task_id not in _TASKS:
        raise CorrectionError("Unknown task; call begin_task before creating entries")
    expires, entries = _TASKS[task_id]
    if expires <= time.monotonic():
        del _TASKS[task_id]
        raise CorrectionError("Task expired; existing entries cannot be adopted by a new task")
    return entries


def _resource(kind, ref, base):
    if kind not in COLLECTIONS:
        raise CorrectionError("Unsupported correction resource")
    path = ref[len(base) :] if ref.startswith(base) else ref
    if not re.fullmatch(rf"{COLLECTIONS[kind]}/[1-9][0-9]*", path):
        raise CorrectionError("Expected an exact FreeAgent resource URL or collection/id path")
    return path


def create(task_id, kind, path, body, call, base):
    with _LOCK:
        # Existing callers retain create compatibility but gain no correction rights.
        task = _task(task_id) if task_id else None
        if task is not None and len(task) >= MAX_ENTRIES:
            raise CorrectionError("Task entry limit reached")
        created = call("POST", path, body)[kind]
        resource = _resource(kind, created["url"], base)
        result = call("GET", resource)
        if task is not None:
            task[resource] = copy.deepcopy(result[kind])
        return result


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


def correct(task_id, kind, ref, confirmed, changes, call, base):
    if confirmed is not True:
        raise CorrectionError("Show the exact correction plan and obtain user confirmation first")
    path = _resource(kind, ref, base)
    with _LOCK:
        task = _task(task_id)
        if path not in task:
            raise CorrectionError("Entry was not created in this task")
        entry = call("GET", path)[kind]
        _eligible(kind, entry)
        if entry != task[path]:
            raise CorrectionError("Entry changed outside this task; report the conflict instead of overwriting it")
        body = {kind: _changes(kind, changes, entry)} if changes is not None else None
        # Revoke before sending: timeout or failed readback must never enable a blind retry.
        del task[path]
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
            task[path] = copy.deepcopy(result[kind])
            return result
        call("DELETE", path)
        try:
            call("GET", path)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return {"deleted": True, "url": base + path}
            raise
        raise CorrectionError("Delete could not be verified: entry still exists; inspect it without retrying")
