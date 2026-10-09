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
    corrections._TASKS.clear()
    task_id = mcp_server.begin_task()["task_id"]
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
    return task_id, entries, calls


def create(task_id, kind):
    if kind == "timeslip":
        return mcp_server.create_timeslip("u", "p", "t", "2026-10-09", "1", task_id=task_id)
    if kind == "invoice":
        return mcp_server.create_draft_invoice("c", "p", "2026-10-09", 30, task_id=task_id)
    if kind == "estimate":
        return mcp_server.create_draft_estimate("c", "2026-10-09", [], task_id=task_id)
    if kind == "expense":
        return mcp_server.create_expense("u", "c", "2026-10-09", "-1", "Train", task_id=task_id)
    return mcp_server.create_bill("c", "B-1", "2026-10-09", "2026-10-31", [], task_id=task_id)


@pytest.mark.parametrize("kind", corrections.COLLECTIONS)
def test_create_update_delete_readbacks(env, kind):
    task_id, entries, calls = env
    result = create(task_id, kind)
    ref = result[kind]["url"]
    out = mcp_server.update_created_entry(kind, ref, {"dated_on": "2026-10-08"}, True, task_id)
    assert out[kind]["dated_on"] == "2026-10-08"
    assert [c[0] for c in calls] == ["POST", "GET", "GET", "PUT", "GET"]
    if kind == "invoice":
        assert all(
            calls[3][2][kind][k] is False
            for k in ("send_new_invoice_emails", "send_reminder_emails", "send_thank_you_emails")
        )
    assert mcp_server.delete_created_entry(kind, ref, True, task_id) == {"deleted": True, "url": ref}
    assert not entries
    assert [c[0] for c in calls[-3:]] == ["GET", "DELETE", "GET"]


def test_requires_task_before_creating(env):
    _, _, calls = env
    task_id = "caller-chosen-task"
    with pytest.raises(ValueError, match="begin_task"):
        create(task_id, "timeslip")
    assert not calls


@pytest.mark.parametrize("case", ["unowned", "new_task", "other_session", "unconfirmed", "bad_url", "bad_fields"])
def test_refuses_before_api_write(env, case):
    task_id, _, calls = env
    create(task_id, "timeslip")
    resource = BASE + "timeslips/1"
    confirmed = True
    changes = {"hours": "2"}
    if case == "unowned":
        resource = BASE + "timeslips/2"
    elif case == "new_task":
        mcp_server.begin_task(previous_task_id=task_id)
    elif case == "other_session":
        task_id = mcp_server.begin_task()["task_id"]
    elif case == "unconfirmed":
        confirmed = False
    elif case == "bad_url":
        resource += "/timer?x=1"
    else:
        changes = {"billed_on_invoice": None}
    calls.clear()
    with pytest.raises(ValueError):
        mcp_server.update_created_entry("timeslip", resource, changes, confirmed, task_id)
    assert all(c[0] == "GET" for c in calls)


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
    task_id, entries, calls = env
    create(task_id, kind)
    path = corrections.COLLECTIONS[kind] + "/1"
    entries[path].update(fields)
    calls.clear()
    with pytest.raises(ValueError):
        if delete:
            mcp_server.delete_created_entry(kind, path, True, task_id)
        else:
            mcp_server.update_created_entry(kind, path, {"dated_on": "2026-10-08"}, True, task_id)
    assert [c[0] for c in calls] == ["GET"]


def test_external_change_is_conflict(env):
    task_id, entries, calls = env
    create(task_id, "timeslip")
    entries["timeslips/1"]["hours"] = "9"
    with pytest.raises(ValueError, match="changed outside"):
        mcp_server.delete_created_entry("timeslip", "timeslips/1", True, task_id)
    assert not any(c[0] == "DELETE" for c in calls)


@pytest.mark.parametrize("kind", ["invoice", "estimate", "bill"])
def test_line_changes_cannot_target_another_entry(env, kind):
    task_id, entries, calls = env
    create(task_id, kind)
    path = corrections.COLLECTIONS[kind] + "/1"
    key = kind + "_items"
    line = {"url": BASE + key + "/7", "description": "Work"}
    entries[path][key] = [line]
    corrections._TASKS[task_id][1][path] = copy.deepcopy(entries[path])
    identity = {"url": line["url"]} if kind == "bill" else {"id": 7}
    out = mcp_server.update_created_entry(kind, path, {key: [{**identity, "description": "Fixed"}]}, True, task_id)
    assert out[kind][key][0]["description"] == "Fixed"
    foreign = {"url": BASE + key + "/8"} if kind == "bill" else {"id": 8}
    writes = len([c for c in calls if c[0] == "PUT"])
    with pytest.raises(ValueError, match="does not belong"):
        mcp_server.update_created_entry(kind, path, {key: [{**foreign, "description": "Wrong"}]}, True, task_id)
    assert len([c for c in calls if c[0] == "PUT"]) == writes


@pytest.mark.parametrize("failure", ["write", "readback", "delete_exists", "delete_403"])
def test_uncertain_outcome_revokes_rights(env, monkeypatch, failure):
    task_id, _, calls = env
    create(task_id, "timeslip")
    original = mcp_server.call
    wrote = False

    def failing(method, path, body=None):
        nonlocal wrote
        if method in {"PUT", "DELETE"}:
            wrote = True
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
    with pytest.raises((TimeoutError, ValueError, urllib.error.HTTPError)):
        if failure.startswith("delete"):
            mcp_server.delete_created_entry("timeslip", "timeslips/1", True, task_id)
        else:
            mcp_server.update_created_entry("timeslip", "timeslips/1", {"hours": "2"}, True, task_id)
    calls.clear()
    with pytest.raises(ValueError, match="not created"):
        mcp_server.delete_created_entry("timeslip", "timeslips/1", True, task_id)
    assert not calls


def test_real_mcp_transport_and_task_isolation(env):
    from mcp.client import Client
    from mcp.client._memory import InMemoryTransport

    async def scenario():
        async with Client(InMemoryTransport(mcp_server.mcp)) as first:
            tools = await first.list_tools()
            for tool in tools.tools:
                assert "ctx" not in tool.input_schema.get("properties", {})
            started = await first.call_tool("begin_task", {})
            assert not started.is_error
            assert started.content[0].type == "text"
            task_id = json.loads(started.content[0].text)["task_id"]
            args = {
                "user": "u",
                "project": "p",
                "task": "t",
                "dated_on": "2026-10-09",
                "hours": "1",
                "task_id": task_id,
            }
            assert not (await first.call_tool("create_timeslip", args)).is_error
            correction = {
                "resource_type": "timeslip",
                "resource": "timeslips/1",
                "changes": {"hours": "2"},
                "confirmed": True,
                "task_id": task_id,
            }
            async with Client(InMemoryTransport(mcp_server.mcp)) as second:
                other = await second.call_tool("begin_task", {})
                assert other.content[0].type == "text"
                assert (
                    await second.call_tool(
                        "update_created_entry", {**correction, "task_id": json.loads(other.content[0].text)["task_id"]}
                    )
                ).is_error
            assert not (await first.call_tool("update_created_entry", correction)).is_error
            await first.call_tool("finish_task", {"task_id": task_id})
            assert (await first.call_tool("update_created_entry", correction)).is_error

    asyncio.run(scenario())


def test_expiry_cannot_adopt_old_entries(env, monkeypatch):
    task_id, _, calls = env
    create(task_id, "timeslip")
    expires = corrections._TASKS[task_id][0]
    monkeypatch.setattr(corrections.time, "monotonic", lambda: expires + 1)
    calls.clear()
    with pytest.raises(ValueError, match="expired"):
        mcp_server.delete_created_entry("timeslip", "timeslips/1", True, task_id)
    new_task = mcp_server.begin_task()["task_id"]
    with pytest.raises(ValueError, match="not created"):
        mcp_server.delete_created_entry("timeslip", "timeslips/1", True, new_task)
    assert not calls


def test_untracked_create_cannot_be_adopted(env):
    task_id, _, _ = env
    mcp_server.create_timeslip("u", "p", "t", "2026-10-09", "1")
    with pytest.raises(ValueError, match="not created"):
        mcp_server.delete_created_entry("timeslip", "timeslips/1", True, task_id)


def test_create_readback_failure_does_not_grant_ownership(env, monkeypatch):
    task_id, _, _ = env
    original = mcp_server.call

    def api(method, path, body=None):
        if method == "GET":
            raise TimeoutError("readback unavailable")
        return original(method, path, body)

    monkeypatch.setattr(mcp_server, "call", api)
    with pytest.raises(TimeoutError):
        create(task_id, "timeslip")
    monkeypatch.setattr(mcp_server, "call", original)
    with pytest.raises(ValueError, match="not created"):
        mcp_server.delete_created_entry("timeslip", "timeslips/1", True, task_id)


def test_estimate_new_line_uses_documented_endpoint(env):
    task_id, _, calls = env
    create(task_id, "estimate")
    item = {"description": "Work", "item_type": "Hours", "quantity": "1", "price": "10"}
    result = mcp_server.update_created_entry(
        "estimate", "estimates/1", {"notes": "Revised", "estimate_items": [item]}, True, task_id
    )
    assert result["estimate"]["notes"] == "Revised"
    assert result["estimate"]["estimate_items"][0]["price"] == "10"
    assert calls[-2] == ("POST", "estimate_items", {"estimate": BASE + "estimates/1", "estimate_item": item})
    assert calls[-3] == ("PUT", "estimates/1", {"estimate": {"notes": "Revised"}})


def test_delete_requires_confirmation_and_restart_loses_rights(env):
    task_id, _, calls = env
    create(task_id, "timeslip")
    calls.clear()
    with pytest.raises(ValueError, match="confirmation"):
        mcp_server.delete_created_entry("timeslip", "timeslips/1", False, task_id)
    corrections._TASKS.clear()
    with pytest.raises(ValueError, match="Unknown task"):
        mcp_server.delete_created_entry("timeslip", "timeslips/1", True, task_id)
    assert not calls


def test_task_and_entry_limits_fail_before_writes(env, monkeypatch):
    task_id, _, calls = env
    monkeypatch.setattr(corrections, "MAX_TASKS", 1)
    with pytest.raises(ValueError, match="Too many"):
        mcp_server.begin_task()
    monkeypatch.setattr(corrections, "MAX_ENTRIES", 1)
    create(task_id, "timeslip")
    calls.clear()
    with pytest.raises(ValueError, match="entry limit"):
        create(task_id, "invoice")
    assert not calls
