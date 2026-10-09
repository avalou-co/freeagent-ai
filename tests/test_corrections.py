"""Correction safety tests use dummy accounting data and mocked API calls."""

import asyncio
import copy
import json
import urllib.error
from email.message import Message

import pytest

mcp_server = pytest.importorskip("freeagent_ai.mcp_server")
from freeagent_ai import corrections  # noqa: E402

BASE = mcp_server.BASE


@pytest.fixture
def env(monkeypatch):
    entries = {}
    calls = []

    def api(method, path, body=None):
        calls.append((method, path, copy.deepcopy(body)))
        if path.startswith("estimate_items/") and method == "PUT":
            assert body is not None
            item_id = path.rsplit("/", 1)[-1]
            for item in entries["estimates/1"]["estimate_items"]:
                if str(item.get("id", item.get("url", "").rsplit("/", 1)[-1])) == item_id:
                    item.update(body["estimate_item"])
            return 200
        if path == "estimate_items" and method == "POST":
            assert body is not None
            entries["estimates/1"].setdefault("estimate_items", []).append(
                {"url": BASE + "estimate_items/99", **body["estimate_item"]}
            )
            return 200
        if method == "POST":
            assert body is not None
            kind = next(iter(body))
            resource = f"{path}/1"
            entries[resource] = {"url": BASE + resource, **body[kind]}
            if kind == "invoice":
                entries[resource]["status"] = "Draft"
            if kind == "bill":
                entries[resource].update(status="Open", paid_value="0.0")
            return {kind: copy.deepcopy(entries[resource])}
        if path not in entries:
            raise urllib.error.HTTPError(BASE + path, 404, "Not found", Message(), None)
        kind = next(k for k, v in corrections.COLLECTIONS.items() if path.startswith(v + "/"))
        if method == "PUT":
            assert body is not None
            entries[path].update(body[kind])
            return 200
        if method == "DELETE":
            del entries[path]
            return 200
        return {kind: copy.deepcopy(entries[path])}

    monkeypatch.setattr(mcp_server, "call", api)
    return entries, calls


def create(kind):
    if kind == "timeslip":
        return mcp_server.create_timeslip("u", "p", "t", "2026-10-09", "1")
    if kind == "invoice":
        return mcp_server.create_draft_invoice("c", "p", "2026-10-09", 30)
    if kind == "estimate":
        return mcp_server.create_draft_estimate("c", "2026-10-09", [])
    if kind == "expense":
        return mcp_server.create_expense("u", "c", "2026-10-09", "-1", "Train")
    return mcp_server.create_bill("c", "B-1", "2026-10-09", "2026-10-31", [])


@pytest.mark.parametrize("kind", corrections.COLLECTIONS)
def test_create_update_delete_readbacks(env, kind):
    entries, calls = env
    result = create(kind)
    ref = result[kind]["url"]
    out = mcp_server.update_created_entry(kind, ref, {"dated_on": "2026-10-08"}, True)
    assert out[kind]["dated_on"] == "2026-10-08"
    assert [c[0] for c in calls] == ["POST", "GET", "GET", "PUT", "GET"]
    if kind == "invoice":
        assert all(
            calls[3][2][kind][k] is False
            for k in ("send_new_invoice_emails", "send_reminder_emails", "send_thank_you_emails")
        )
    assert mcp_server.delete_created_entry(kind, ref, True) == {"deleted": True, "url": ref}
    assert not entries
    assert [c[0] for c in calls[-3:]] == ["GET", "DELETE", "GET"]


@pytest.mark.parametrize("delete", [False, True])
def test_confirmation_required_before_api_calls(env, delete):
    _, calls = env
    with pytest.raises(ValueError, match="confirmation"):
        if delete:
            mcp_server.delete_created_entry("timeslip", "timeslips/1", False)
        else:
            mcp_server.update_created_entry("timeslip", "timeslips/1", {"hours": "2"}, False)
    assert not calls


@pytest.mark.parametrize(
    "resource", ["https://evil.example/timeslips/1", "timeslips/1/timer", "timeslips/1?x=1", "../timeslips/1"]
)
def test_invalid_paths_refused_before_api_calls(env, resource):
    _, calls = env
    with pytest.raises(ValueError):
        mcp_server.delete_created_entry("timeslip", resource, True)
    assert not calls


@pytest.mark.parametrize(
    "changes", [{}, {"status": "Draft"}, {"billed_on_invoice": None}, {"send_new_invoice_emails": True}]
)
def test_unsupported_changes_do_not_write(env, changes):
    _, calls = env
    create("timeslip")
    calls.clear()
    with pytest.raises(ValueError):
        mcp_server.update_created_entry("timeslip", "timeslips/1", changes, True)
    assert [c[0] for c in calls] == ["GET"]


@pytest.mark.parametrize(
    "kind,fields",
    [
        ("timeslip", {"billed_on_invoice": BASE + "invoices/2"}),
        ("timeslip", {"timer": {"running": True}}),
        ("invoice", {"status": "Open"}),
        ("invoice", {"status": "Scheduled To Email"}),
        ("estimate", {"status": "Sent"}),
        ("expense", {"rebilled_on_invoice": BASE + "invoices/2"}),
        ("bill", {"paid_value": "1.0"}),
        ("bill", {"paid_value": "NaN"}),
        ("bill", {"rebilled_on_invoice_item": BASE + "invoice_items/2"}),
    ],
)
@pytest.mark.parametrize("delete", [False, True])
def test_protected_statuses_block_update_and_delete(env, kind, fields, delete):
    entries, calls = env
    create(kind)
    path = corrections.COLLECTIONS[kind] + "/1"
    entries[path].update(fields)
    calls.clear()
    with pytest.raises(ValueError):
        if delete:
            mcp_server.delete_created_entry(kind, path, True)
        else:
            mcp_server.update_created_entry(kind, path, {"dated_on": "2026-10-08"}, True)
    assert [c[0] for c in calls] == ["GET"]


@pytest.mark.parametrize("kind", ["invoice", "estimate", "bill"])
def test_line_changes_cannot_target_another_entry(env, kind):
    entries, calls = env
    create(kind)
    path = corrections.COLLECTIONS[kind] + "/1"
    key = kind + "_items"
    line = {"url": BASE + key + "/7", "description": "Work"}
    entries[path][key] = [line]
    identity = {"url": line["url"]} if kind == "bill" else {"id": 7}
    out = mcp_server.update_created_entry(kind, path, {key: [{**identity, "description": "Fixed"}]}, True)
    assert out[kind][key][0]["description"] == "Fixed"
    foreign = {"url": BASE + key + "/8"} if kind == "bill" else {"id": 8}
    writes = len([c for c in calls if c[0] == "PUT"])
    with pytest.raises(ValueError, match="does not belong"):
        mcp_server.update_created_entry(kind, path, {key: [{**foreign, "description": "Wrong"}]}, True)
    assert len([c for c in calls if c[0] == "PUT"]) == writes


@pytest.mark.parametrize("failure", ["write", "readback", "delete_exists", "delete_403"])
def test_uncertain_outcomes_surface_without_automatic_retry(env, monkeypatch, failure):
    _, _ = env
    create("timeslip")
    original = mcp_server.call
    wrote = False
    writes = []

    def failing(method, path, body=None):
        nonlocal wrote
        if method in {"PUT", "DELETE"}:
            wrote = True
            writes.append(method)
            if failure == "write":
                raise TimeoutError("unknown outcome")
            if failure.startswith("delete"):
                return 200
        if method == "GET" and wrote:
            if failure == "readback":
                raise TimeoutError("readback unavailable")
            if failure == "delete_403":
                raise urllib.error.HTTPError(BASE + path, 403, "Forbidden", Message(), None)
        return original(method, path, body)

    monkeypatch.setattr(mcp_server, "call", failing)
    with pytest.raises(ValueError, match="inspect FreeAgent without retrying"):
        if failure.startswith("delete"):
            mcp_server.delete_created_entry("timeslip", "timeslips/1", True)
        else:
            mcp_server.update_created_entry("timeslip", "timeslips/1", {"hours": "2"}, True)
    assert len(writes) == 1


def test_real_mcp_transport_needs_no_task_lifecycle(env):
    from mcp.client import Client
    from mcp.client._memory import InMemoryTransport

    async def scenario():
        async with Client(InMemoryTransport(mcp_server.mcp)) as client:
            tools = await client.list_tools()
            assert not {"begin_task", "finish_task"} & {t.name for t in tools.tools}
            assert all("task_id" not in t.input_schema.get("properties", {}) for t in tools.tools)
            args = {"user": "u", "project": "p", "task": "t", "dated_on": "2026-10-09", "hours": "1"}
            assert not (await client.call_tool("create_timeslip", args)).is_error
            correction = {
                "resource_type": "timeslip",
                "resource": "timeslips/1",
                "changes": {"hours": "2"},
                "confirmed": False,
            }
            assert (await client.call_tool("update_created_entry", correction)).is_error
            updated = await client.call_tool("update_created_entry", {**correction, "confirmed": True})
            assert not updated.is_error
            assert updated.content[0].type == "text"
            assert json.loads(updated.content[0].text)["timeslip"]["hours"] == "2"
            deleted = await client.call_tool(
                "delete_created_entry", {"resource_type": "timeslip", "resource": "timeslips/1", "confirmed": True}
            )
            assert not deleted.is_error
            assert deleted.content[0].type == "text"
            assert json.loads(deleted.content[0].text)["deleted"] is True

    asyncio.run(scenario())


def test_estimate_new_line_uses_documented_endpoint(env):
    _, calls = env
    create("estimate")
    item = {"description": "Work", "item_type": "Hours", "quantity": "1", "price": "10"}
    result = mcp_server.update_created_entry(
        "estimate", "estimates/1", {"notes": "Revised", "estimate_items": [item]}, True
    )
    assert result["estimate"]["notes"] == "Revised"
    assert result["estimate"]["estimate_items"][0]["price"] == "10"
    assert calls[-2] == ("POST", "estimate_items", {"estimate": BASE + "estimates/1", "estimate_item": item})
    assert calls[-3] == ("PUT", "estimates/1", {"estimate": {"notes": "Revised"}})
