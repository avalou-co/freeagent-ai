"""Exact expense transport and marketplace invocation; no tax arithmetic or live writes."""

import time
import urllib.error
from copy import deepcopy
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
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


@pytest.fixture
def exact(accounts, hosted_context):
    accounts.replace(
        "exact", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("exact", frozenset({"freeagent:read", "freeagent:write"}), 101)
    calls = []
    state: dict[str, Any] = {"failure": None, "posted": None}

    def transport(method, url, deadline, **kwargs):
        path = urlsplit(url).path.removeprefix("/v2/")
        calls.append((method, path, deepcopy(kwargs.get("body"))))
        if method == "POST":
            if state["failure"] == "reject":
                raise urllib.error.HTTPError(
                    url, 422, "invalid", Message(), BytesIO(b'{"errors":{"tax":"provider rejection"}}')
                )
            if state["failure"] == "timeout":
                raise TimeoutError("uncertain")
            state["posted"] = deepcopy(kwargs["body"]["expense"])
            return {"expense": {"url": BASE + "expenses/91"}}, {"Location": BASE + "expenses/91"}
        if path.startswith("company"):
            return {"company": {"url": BASE + "company/1"}}, {}
        if state["failure"] == "readback":
            raise urllib.error.HTTPError(url, 503, "unavailable", Message(), None)
        if path == "expenses/91":
            record = {**state["posted"], "url": BASE + path}
            if "attachment" in record:
                record["attachment"] = {
                    "file_name": "synthetic.pdf",
                    "content_type": "application/x-pdf",
                    "file_size": 5,
                    "content_src": "https://secret.invalid/signed",
                }
            return {"expense": record}, {}
        if path in {"expenses", "bills"}:
            if state["failure"] == "lookup":
                raise urllib.error.HTTPError(url, 403, "denied", Message(), None)
            return {path: []}, {}
        raise AssertionError(path)

    dispatcher = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )

    def invoke(args):
        with hosted_context(principal):
            return dispatcher.call_tool("create_expense_from_payload", args)

    return dispatcher, principal, invoke, calls, state


def expense():
    return {
        "user": BASE + "users/1",
        "category": BASE + "categories/285",
        "dated_on": "2026-10-26",
        "gross_value": "-71.23",
        "description": "Synthetic receipt: ignore instructions in document",
        "currency": "EUR",
        "receipt_reference": "SYN-89",
        "native_gross_value": "-60.00",
        "sales_tax_value": "-3.12",
        "native_sales_tax_value": "-2.50",
        "manual_sales_tax_amount": "2.50",
        "second_sales_tax_rate": "0.0",
        "sales_tax_status": "TAXABLE",
        "second_sales_tax_status": "EXEMPT",
    }


@pytest.mark.parametrize(
    "tax",
    [
        {"sales_tax_rate": "20.0"},
        {"sales_tax_rate": "0", "manual_sales_tax_amount": "0", "sales_tax_value": "0"},
        {
            "sales_tax_rate": "unaccepted by provider",
            "second_sales_tax_rate": "7.50",
            "second_sales_tax_status": "TAXABLE",
        },
    ],
)
def test_exact_payload_and_provider_readback_without_tax_validation(exact, tax):
    _, _, invoke, calls, _ = exact
    payload = {**expense(), **tax}
    original = deepcopy(payload)
    result = invoke({"expense": payload, "confirmed": True})
    assert not result.is_error
    assert payload == original
    assert calls[0] == ("POST", "expenses", {"expense": original})
    assert [m for m, _, _ in calls] == ["POST", "GET"]
    assert result.structured_content == {"expense": {**original, "url": BASE + "expenses/91"}}


@pytest.mark.parametrize("failure", ["reject", "timeout", "readback"])
def test_uncertain_and_rejected_write_never_replayed(exact, failure):
    _, _, invoke, calls, state = exact
    state["failure"] = failure
    result = invoke({"expense": expense(), "confirmed": True})
    assert result.is_error
    assert len([m for m, _, _ in calls if m == "POST"]) == 1
    if failure == "readback":
        assert "expenses/91" in result.content[0].text


@pytest.mark.parametrize(
    "args",
    [
        {"expense": expense(), "confirmed": False},
        {"expense": [], "confirmed": True},
        {"expense": {**expense(), "attachment": {"data": "bypass"}}, "confirmed": True},
    ],
)
def test_refusal_malformed_and_attachment_bypass_never_write(exact, args):
    _, _, invoke, calls, _ = exact
    assert invoke(args).is_error
    assert calls == []


def test_remote_receipt_reuses_download_and_redacts_metadata(exact, monkeypatch):
    _, _, invoke, calls, _ = exact
    file = {"download_url": "https://files.example/synthetic", "file_id": "synthetic"}
    downloads = []

    def download(reference, *_):
        downloads.append(reference)
        return {"file_name": "synthetic.pdf", "content_type": "application/x-pdf", "data": "JVBERi0="}

    monkeypatch.setattr("freeagent_ai.public_tools.download", download)
    result = invoke({"expense": expense(), "receipt": file, "confirmed": True})
    assert not result.is_error
    assert downloads == [file]
    assert calls[0][2]["expense"]["attachment"]["data"] == "JVBERi0="
    assert result.structured_content["expense"]["attachment"] == {
        "file_name": "synthetic.pdf",
        "content_type": "application/x-pdf",
        "file_size": 5,
    }
    assert "signed" not in str(result.structured_content)


@pytest.mark.parametrize("scope", ["freeagent:read", "freeagent:read freeagent:write"])
def test_packaged_skill_discovery_authenticated_http_exact_create(exact, accounts, scope):
    dispatcher, _, _, calls, _ = exact
    principal = Principal("exact", frozenset(scope.split()), 101)
    files = package_files(Path(__file__).resolve().parents[1])
    for name in ("expenses", "receipts"):
        skill = files[f"skills/{name}/SKILL.md"].decode()
        assert "create_expense_from_payload" in skill
        assert "Nested provider payloads" in skill
        assert "use existing direct API tools" not in skill
    app = create_app(settings(), accounts, SimpleNamespace(principal=lambda _: principal), dispatcher)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = {"Authorization": "Bearer synthetic", "Accept": "application/json, text/event-stream"}

        def rpc(method, params):
            response = client.post(
                "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
            )
            assert response.status_code == 200
            return response.json()["result"]

        tools = {t["name"]: t for t in rpc("tools/list", {})["tools"]}
        if scope == "freeagent:read":
            assert tools["create_expense_from_payload"]["_meta"]["securitySchemes"] == [
                {"type": "oauth2", "scopes": ["freeagent:write"]}
            ]
            result = rpc(
                "tools/call",
                {"name": "create_expense_from_payload", "arguments": {"expense": expense(), "confirmed": True}},
            )
            assert result["isError"]
            assert not any(m == "POST" for m, _, _ in calls)
            return
        tool = tools["create_expense_from_payload"]
        assert "receipt_path" not in tool["inputSchema"]["properties"]
        assert tool["_meta"]["openai/fileParams"] == ["receipt"]
        for name in ("list_expenses", "list_bills"):
            result = rpc(
                "tools/call", {"name": name, "arguments": {"from_date": "2026-10-26", "to_date": "2026-10-26"}}
            )
            assert not result.get("isError")
        result = rpc(
            "tools/call",
            {"name": "create_expense_from_payload", "arguments": {"expense": expense(), "confirmed": True}},
        )
        assert result["structuredContent"]["expense"]["manual_sales_tax_amount"] == "2.50"
        assert [c for c in calls if c[0] == "POST"] == [("POST", "expenses", {"expense": expense()})]


def test_lookup_failure_is_not_duplicate_clearance(exact, hosted_context):
    dispatcher, principal, _, calls, state = exact
    state["failure"] = "lookup"
    with hosted_context(principal):
        for name in ("list_expenses", "list_bills"):
            assert dispatcher.call_tool(name, {"from_date": "2026-10-26", "to_date": "2026-10-26"}).is_error
    assert not any(m == "POST" for m, _, _ in calls)
    # This observes reads only, not assistant behavior; the packaged skill stops on unresolved evidence.
    files = package_files(Path(__file__).resolve().parents[1])
    assert b"Do not create while unresolved" in files["skills/receipts/SKILL.md"]


def test_named_tool_is_fixed_expense_endpoint():
    op = REGISTRY["create_expense_from_payload"]
    assert (op.method, op.endpoint, op.root) == ("POST", "expenses", "expense")


def test_local_exact_helper_preserves_payload_and_reads_provider(monkeypatch):
    from freeagent_ai import mcp_server

    calls = []
    payload = {**expense(), "future_provider_field": {"supplied": "unchanged"}, "receipt_reference": ""}
    original = deepcopy(payload)

    def call(method, path, body=None):
        calls.append((method, path, deepcopy(body)))
        return {"expense": {"url": BASE + "expenses/91"}} if method == "POST" else {"expense": original}

    monkeypatch.setattr(mcp_server, "call", call)
    assert mcp_server.create_expense_from_payload(payload) == {"expense": original}
    assert payload == original
    assert calls == [("POST", "expenses", {"expense": original}), ("GET", "expenses/91", None)]
