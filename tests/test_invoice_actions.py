"""Synthetic named invoice actions, not live sends or assistant-approval evidence."""

import json
import time
import urllib.error
from copy import deepcopy
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from conftest import settings
from starlette.testclient import TestClient

from freeagent_ai.hosted_accounts import Principal
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.public_package import package_files
from freeagent_ai.public_tools import REGISTRY, Dispatcher

BASE = "https://api.freeagent.com/v2/"
ACTIONS = ("duplicate_invoice", "mark_invoice_as_sent", "send_invoice_email")
EMAIL = {
    "to": "reviewed@example.invalid",
    "from": "registered@example.invalid",
    "subject": "Exact approved subject",
    "body": "Exact approved message. No template substitution.",
    "email_to_sender": False,
}


def arguments(name, **changes):
    return {
        "id": "1",
        "confirmed": True,
        **({"email": deepcopy(EMAIL)} if name == "send_invoice_email" else {}),
        **changes,
    }


@pytest.fixture
def actions(accounts):
    accounts.replace(
        "actions", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("actions", frozenset({"freeagent:read", "freeagent:write"}), 101)
    denied = Principal("actions", frozenset({"freeagent:read"}), 101)
    calls, state = [], {"failure": None, "writes": 0}
    rows = {
        "1": {
            "url": BASE + "invoices/1",
            "status": "Draft",
            "reference": "SOURCE",
            "currency": "GBP",
            "total_value": "123.45",
            "send_new_invoice_emails": False,
            "send_reminder_emails": False,
            "send_thank_you_emails": False,
        },
        "2": {
            "url": BASE + "invoices/2",
            "status": "Draft",
            "reference": "PROVIDER-NEXT",
            "dated_on": "2026-10-29",
            "currency": "GBP",
            "send_new_invoice_emails": False,
            "send_reminder_emails": False,
            "send_thank_you_emails": False,
        },
    }

    def transport(method, url, deadline, **kwargs):
        path = urlsplit(url).path.removeprefix("/v2/")
        calls.append((method, path, deepcopy(kwargs.get("body"))))
        if method != "GET":
            state["writes"] += 1
            if state["failure"] == "reject":
                raise urllib.error.HTTPError(url, 422, "invalid", Message(), BytesIO(json.dumps(EMAIL).encode()))
            if state["failure"] == "timeout":
                raise TimeoutError("uncertain")
            if state["failure"] == "disconnect":
                accounts.disconnect("actions", 101)
            if path == "invoices/1/duplicate":
                target = (
                    "https://other.example.invalid/invoices/2"
                    if state["failure"] == "identity"
                    else BASE + "invoices/2"
                )
                return {"invoice": {"url": target}}, {}
            if path == "invoices/1/transitions/mark_as_sent":
                rows["1"]["status"] = "Open"
                return 200, {}
            assert path == "invoices/1/send_email"
            return 200, {}
        if state["failure"] == "readback" or (state["failure"] == "source_readback" and path == "invoices/1"):
            raise urllib.error.HTTPError(url, 503, "unavailable", Message(), BytesIO(json.dumps(EMAIL).encode()))
        if state["failure"] == "malformed":
            return {"invoice": {"invoice_items": "not an array"}}, {}
        if state["failure"] == "read_identity":
            return {"invoice": {"url": BASE + "invoices/999"}}, {}
        return {"invoice": deepcopy(rows[path.split("/")[-1]])}, {}

    dispatcher = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    verifier = SimpleNamespace(principal=lambda token: denied if token == "denied" else principal)
    with TestClient(create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN) as client:

        def rpc(method, params=None, token="write"):
            result = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            )
            assert result.status_code == 200
            return result.json()["result"]

        yield rpc, calls, state, rows


def invoke(rpc, name, args=None, token="write"):
    return rpc("tools/call", {"name": name, "arguments": args if args is not None else arguments(name)}, token)


def test_packaged_invoice_actions_are_discovered_with_approval_and_correct_annotations(actions):
    rpc, calls, _, _ = actions
    files = package_files(Path(__file__).resolve().parents[1])
    tools = {tool["name"]: tool for tool in rpc("tools/list")["tools"]}
    audit = {tool["name"]: tool for tool in json.loads(files["docs/public-tool-audit.json"])}
    skill = files["skills/invoicing/SKILL.md"].decode()
    for name in ACTIONS:
        assert name in skill
        assert tools[name]["inputSchema"] == audit[name]["inputSchema"]
        assert tools[name]["securitySchemes"] == [{"type": "oauth2", "scopes": ["freeagent:write"]}]
        assert "confirmed" in tools[name]["inputSchema"]["required"]
        assert not tools[name]["annotations"]["idempotentHint"]
    assert tools["send_invoice_email"]["annotations"]["openWorldHint"]
    assert tools["send_invoice_email"]["annotations"]["destructiveHint"]
    assert tools["mark_invoice_as_sent"]["annotations"]["openWorldHint"]
    assert "This workflow remains read-only" in files["skills/invoice-status/SKILL.md"].decode()
    assert "this\n   user request" in skill
    assert "missing ownership" in skill
    assert "recipient_delivery" in skill
    assert not calls


def test_duplicate_reads_new_invoice_and_original_without_changing_source(actions):
    rpc, calls, _, rows = actions
    source = deepcopy(rows["1"])
    result = invoke(rpc, "duplicate_invoice")
    assert not result["isError"]
    assert calls == [("POST", "invoices/1/duplicate", None), ("GET", "invoices/2", None), ("GET", "invoices/1", None)]
    actual = result["structuredContent"]
    assert actual["invoice"] == rows["2"]
    assert actual["source_invoice"] == source == rows["1"]


def test_mark_sent_uses_only_exact_transition_then_reads_accounting_state(actions):
    rpc, calls, _, _ = actions
    result = invoke(rpc, "mark_invoice_as_sent")
    assert not result["isError"]
    assert calls == [("PUT", "invoices/1/transitions/mark_as_sent", None), ("GET", "invoices/1", None)]
    assert result["structuredContent"]["invoice"]["status"] == "Open"
    assert "request_accepted" not in result["structuredContent"]


@pytest.mark.parametrize("copy", [False, True])
def test_email_forwards_exact_fields_and_separates_acceptance_from_recipient_delivery(actions, copy):
    rpc, calls, _, _ = actions
    email = {**EMAIL, "email_to_sender": copy}
    result = invoke(rpc, "send_invoice_email", arguments("send_invoice_email", email=email))
    assert not result["isError"]
    assert calls == [
        ("POST", "invoices/1/send_email", {"invoice": {"email": {**email, "attach_expense_receipts": False}}}),
        ("GET", "invoices/1", None),
    ]
    assert email == {**EMAIL, "email_to_sender": copy}
    data = result["structuredContent"]
    assert data["request_accepted"] is True
    assert data["recipient_delivery"] == "unavailable"
    assert data["invoice"]["status"] == "Draft"  # Acceptance never fabricates a status change.
    assert EMAIL["body"] not in str(result)


@pytest.mark.parametrize("name", ACTIONS)
@pytest.mark.parametrize("mode", ["refused", "scope", "missing"])
def test_unapproved_or_unauthorized_action_never_reaches_provider(actions, name, mode):
    rpc, calls, _, _ = actions
    args = arguments(name, confirmed=False) if mode == "refused" else arguments(name)
    if mode == "missing":
        args.pop("confirmed")
    assert invoke(rpc, name, args, "denied" if mode == "scope" else "write")["isError"]
    assert not calls


@pytest.mark.parametrize("field", ["to", "from", "subject", "body", "email_to_sender"])
def test_unresolved_email_fields_do_not_get_guessed_defaults(actions, field):
    rpc, calls, _, _ = actions
    args = arguments("send_invoice_email")
    del args["email"][field]
    assert invoke(rpc, "send_invoice_email", args)["isError"]
    assert not calls


@pytest.mark.parametrize(
    "extra",
    [{"use_template": True}, {"attachments": []}, {"attach_expense_receipts": True}, {"cc": "other@example.invalid"}],
)
def test_unsupported_template_receipt_and_attachment_modes_are_not_silently_ignored(actions, extra):
    rpc, calls, _, _ = actions
    args = arguments("send_invoice_email", email={**EMAIL, **extra})
    assert invoke(rpc, "send_invoice_email", args)["isError"]
    assert not calls


@pytest.mark.parametrize("name", ACTIONS)
@pytest.mark.parametrize("failure", ["reject", "timeout", "readback", "malformed", "disconnect", "read_identity"])
def test_failed_or_uncertain_action_is_not_replayed_and_email_content_is_not_exposed(actions, name, failure):
    rpc, calls, state, _ = actions
    state["failure"] = failure
    result = invoke(rpc, name)
    assert result["isError"]
    assert state["writes"] == 1
    assert len([call for call in calls if call[0] != "GET"]) == 1
    assert "original company" in str(result)
    for value in (EMAIL["to"], EMAIL["from"], EMAIL["subject"], EMAIL["body"]):
        assert value not in str(result)


@pytest.mark.parametrize("failure", ["identity", "source_readback"])
def test_duplicate_invalid_identity_or_partial_readback_is_unverified_without_new_writes(actions, failure):
    rpc, calls, state, _ = actions
    state["failure"] = failure
    result = invoke(rpc, "duplicate_invoice")
    assert result["isError"]
    assert state["writes"] == 1
    assert all("other.example.invalid" not in path for _, path, _ in calls)
    assert "retry" in str(result) or "further action" in str(result)


def test_arbitrary_transitions_sending_alias_and_payment_execution_are_unavailable():
    for name in (
        "send_invoice",
        "mark_invoice_as_cancelled",
        "mark_invoice_as_draft",
        "mark_invoice_as_scheduled",
        "take_invoice_payment",
    ):
        assert name not in REGISTRY
