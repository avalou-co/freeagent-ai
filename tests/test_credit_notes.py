"""Synthetic authenticated credit mechanics; no live writes or assistant behavior claims."""

import hashlib
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


@pytest.fixture
def credit(accounts, hosted_context):
    accounts.replace(
        "credit", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("credit", frozenset({"freeagent:read", "freeagent:write"}), 101)
    calls = []
    state = {
        "credit_note": dict(
            url=BASE + "credit_notes/8",
            contact=BASE + "contacts/1",
            currency="EUR",
            status="Draft",
            due_value="-120",
            refunded_value="0",
            total_value="-120",
            credit_note_items=[dict(description="credit", quantity="1", price="-100", sales_tax_rate="20")],
        ),
        "invoice": dict(url=BASE + "invoices/7", currency="EUR", status="Open", due_value="60"),
        "credit_note_reconciliation": dict(
            url=BASE + "credit_note_reconciliations/9",
            credit_note=BASE + "credit_notes/8",
            invoice=BASE + "invoices/7",
            gross_value="60",
            currency="EUR",
            exchange_rate="0.85",
        ),
        "failure": None,
    }

    def transport(method, url, deadline, **kwargs):
        path = urlsplit(url).path.removeprefix("/v2/")
        calls.append((method, path, kwargs.get("body")))
        if method == "PUT":
            assert path == "credit_notes/8/transitions/mark_as_sent"
            if state["failure"] == "reject":
                raise urllib.error.HTTPError(url, 422, "invalid", Message(), None)
            if state["failure"] == "timeout":
                raise TimeoutError("uncertain")
            state["credit_note"]["status"] = "Open"
            return 200, {}
        if method == "POST":
            if state["failure"] == "reject":
                raise urllib.error.HTTPError(
                    url, 422, "invalid", Message(), BytesIO(b'{"errors":{"gross_value":"too much"}}')
                )
            if state["failure"] == "timeout":
                raise TimeoutError("uncertain")
            root = "credit_note" if path == "credit_notes" else "credit_note_reconciliation"
            return {root: deepcopy(state[root])}, {"Location": state[root]["url"]}
        if path.startswith("company"):
            return {"company": {"url": BASE + "company/1"}}, {}
        if state["failure"] == "readback" or (state["failure"] == "invoice_readback" and path == "invoices/7"):
            raise urllib.error.HTTPError(url, 503, "unavailable", Message(), None)
        if state["failure"] == "malformed" and path == "credit_notes/8":
            return {"credit_note": "invalid"}, {}
        if path == "credit_notes":
            return {"credit_notes": [deepcopy(state["credit_note"])]}, {}
        if path == "credit_note_reconciliations":
            return {"credit_note_reconciliations": [deepcopy(state["credit_note_reconciliation"])]}, {}
        root = (
            "credit_note_reconciliation"
            if path.startswith("credit_note_reconciliations/")
            else "credit_note"
            if path.startswith("credit_notes/")
            else "invoice"
        )
        output = "credit_note_reconciliations" if root == "credit_note_reconciliation" else root
        return {output: deepcopy(state[root])}, {}

    dispatcher = Dispatcher(
        accounts, "dummy", "dummy", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )

    def invoke(name, **args):
        with hosted_context(principal):
            return dispatcher.call_tool(name, args)

    return invoke, state, calls, dispatcher


def draft_args():
    return dict(
        contact="1",
        dated_on="2026-10-25",
        payment_terms_in_days=0,
        items=[dict(description="credit", quantity="1", price="-100", sales_tax_rate="20")],
        currency="EUR",
        confirmed=True,
    )


def allocation_args():
    return dict(
        credit_note="8",
        invoice="7",
        gross_value="60",
        dated_on="2026-10-25",
        currency="EUR",
        exchange_rate="0.85",
        confirmed=True,
    )


def test_draft_signed_foreign_currency_and_provider_default(credit):
    invoke, state, calls, _ = credit
    result = invoke("create_draft_credit_note", **draft_args())
    assert not result.is_error
    assert result.structured_content == {"credit_note": state["credit_note"]}
    writes = [c for c in calls if c[0] == "POST"]
    assert len(writes) == 1
    body = writes[0][2]["credit_note"]
    assert body["contact"] == BASE + "contacts/1"
    assert body["credit_note_items"] == draft_args()["items"]
    assert body["currency"] == "EUR"
    assert "status" not in body
    assert not any("transitions" in path or "send_email" in path for _, path, _ in calls)


@pytest.mark.parametrize("amount", ["60", "120", "999"])
def test_allocation_reads_all_affected_records_without_local_accounting_validation(credit, amount):
    invoke, state, calls, _ = credit
    state["credit_note_reconciliation"]["gross_value"] = amount
    state["credit_note"]["status"] = "Open"
    result = invoke("create_credit_note_reconciliation", **{**allocation_args(), "gross_value": amount})
    assert not result.is_error
    assert result.structured_content == {k: state[k] for k in ("credit_note_reconciliation", "credit_note", "invoice")}
    write = next(c for c in calls if c[0] == "POST")
    assert write[2]["credit_note_reconciliation"]["invoice"] == BASE + "invoices/7"
    assert write[2]["credit_note_reconciliation"]["credit_note"] == BASE + "credit_notes/8"
    assert write[2]["credit_note_reconciliation"]["gross_value"] == amount
    assert {p for m, p, _ in calls if m == "GET"} >= {"credit_note_reconciliations/9", "credit_notes/8", "invoices/7"}


@pytest.mark.parametrize(
    "name,args", [("create_draft_credit_note", draft_args()), ("create_credit_note_reconciliation", allocation_args())]
)
def test_refused_writes_never_reach_provider(credit, name, args):
    invoke, _, calls, _ = credit
    result = invoke(name, **{**args, "confirmed": False})
    assert result.is_error
    assert not calls


@pytest.mark.parametrize("failure", ["reject", "timeout", "readback"])
@pytest.mark.parametrize(
    "name,args", [("create_draft_credit_note", draft_args()), ("create_credit_note_reconciliation", allocation_args())]
)
def test_provider_rejection_and_uncertain_outcomes_never_replay(credit, failure, name, args):
    invoke, state, calls, _ = credit
    state["failure"] = failure
    result = invoke(name, **args)
    assert result.is_error
    assert len([c for c in calls if c[0] == "POST"]) == 1
    if failure != "reject":
        assert "inspect" in result.content[0].text.lower()
    if failure == "reject":
        assert "422" in result.content[0].text


def test_existing_draft_and_allocation_evidence_available_for_duplicate_review(credit):
    invoke, state, calls, _ = credit
    note = invoke("list_credit_notes", contact="1", nested_credit_note_items="true")
    reconciliations = invoke("list_credit_note_reconciliations")
    assert note.structured_content["credit_notes"][0]["status"] == "Draft"
    assert reconciliations.structured_content["credit_note_reconciliations"][0]["invoice"] == state["invoice"]["url"]
    assert not [c for c in calls if c[0] == "POST"]


def test_duplicate_lookup_failure_is_explicitly_incomplete(credit):
    invoke, state, calls, _ = credit
    state["failure"] = "readback"
    result = invoke("list_credit_notes", contact="1")
    assert result.is_error
    assert "incomplete" in result.content[0].text.lower()
    assert not [c for c in calls if c[0] == "POST"]


def test_allocation_is_destructive_non_idempotent_and_policy_gated():
    descriptor = REGISTRY["create_credit_note_reconciliation"].descriptor
    assert descriptor.annotations.destructive_hint
    assert not descriptor.annotations.idempotent_hint
    assert "ownership exception" in descriptor.description
    assert "existing issued credit" in descriptor.description
    assert "separate approval" in descriptor.description
    assert "No issuing, invoice edits, cash refunds" in descriptor.description


def test_existing_issued_allocation_partial_verification_never_repeats_or_edits(credit):
    invoke, state, calls, _ = credit
    state["credit_note"]["status"] = "Open"
    state["failure"] = "invoice_readback"
    result = invoke("create_credit_note_reconciliation", **allocation_args())
    assert result.is_error
    assert "readback was not verified" in result.content[0].text
    assert len([c for c in calls if c[0] == "POST"]) == 1
    assert any(m == "GET" and p == "credit_notes/8" for m, p, _ in calls)
    assert any(m == "GET" and p == "invoices/7" for m, p, _ in calls)
    assert not any(m in {"PUT", "DELETE"} or "transitions" in p or "send_email" in p for m, p, _ in calls)


def test_credit_issuance_is_fixed_destructive_and_separate_from_email_refund():
    operation = REGISTRY["issue_credit_note"]
    assert (operation.method, operation.endpoint) == ("PUT", "credit_notes/{id}/transitions/mark_as_sent")
    assert operation.descriptor.annotations.destructive_hint
    assert not operation.descriptor.annotations.idempotent_hint
    assert "separate issuance approval" in operation.descriptor.description
    assert not any("credit_note" in name and any(x in name for x in ("refund", "email")) for name in REGISTRY)


def test_issuance_refusal_reaches_no_provider(credit):
    invoke, _, calls, _ = credit
    assert invoke("issue_credit_note", id="8", confirmed=False).is_error
    assert calls == []


@pytest.mark.parametrize("failure", ["timeout", "reject", "readback", "malformed"])
def test_issuance_uncertain_outcomes_do_not_replay(credit, failure):
    invoke, state, calls, _ = credit
    state["failure"] = failure
    result = invoke("issue_credit_note", id="8", confirmed=True)
    assert result.is_error
    assert "inspect this credit in the original company before any retry" in result.content[0].text
    assert len([call for call in calls if call[0] == "PUT"]) == 1
    assert not any(method in {"POST", "DELETE"} for method, _, _ in calls)
    if failure == "reject":
        assert "FreeAgent HTTP 422" in result.content[0].text
    if failure == "readback":
        assert state["credit_note"]["status"] == "Open"
        assert any(path == "credit_notes/8" for _, path, _ in calls)


def test_issuance_requires_write_scope_and_numeric_id(credit, hosted_context):
    _, _, calls, dispatcher = credit
    with hosted_context(Principal("credit", frozenset({"freeagent:read"}), 101)):
        assert dispatcher.call_tool("issue_credit_note", {"id": "8", "confirmed": True}).is_error
    assert calls == []
    with hosted_context(Principal("credit", frozenset({"freeagent:write"}), 101)):
        assert dispatcher.call_tool("issue_credit_note", {"id": "8/transitions/other", "confirmed": True}).is_error
    assert calls == []


def test_marketplace_package_and_remote_mcp_credit_path(credit, accounts):
    _, state, calls, dispatcher = credit
    root = Path(__file__).resolve().parents[1]
    files = package_files(root)
    skill = files["skills/credit-notes/SKILL.md"].decode()
    assert "No client-local Python" in skill
    assert "freeagent_get" not in skill
    assert "docs/credit-notes.md" in files
    principal = Principal("credit", frozenset({"freeagent:read", "freeagent:write"}), 101)
    app = create_app(settings(), accounts, SimpleNamespace(principal=lambda _: principal), dispatcher)
    with TestClient(app, base_url=ORIGIN) as client:
        headers = {"Authorization": "Bearer synthetic", "Accept": "application/json, text/event-stream"}
        discovery = client.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
        )
        descriptors = {t["name"]: t for t in discovery.json()["result"]["tools"]}
        for name, args in [
            ("create_draft_credit_note", draft_args()),
            ("issue_credit_note", {"id": "8", "confirmed": True}),
            ("create_credit_note_reconciliation", allocation_args()),
        ]:
            assert name in descriptors
            assert descriptors[name]["securitySchemes"] == [{"type": "oauth2", "scopes": ["freeagent:write"]}]
            response = client.post(
                "/mcp",
                headers=headers,
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": name, "arguments": args}},
            )
            assert response.status_code == 200
            result = response.json()["result"]
            assert not result.get("isError", False)
            data = result["structuredContent"]
            assert "credit_note" in data
            if name == "issue_credit_note":
                assert data["credit_note"]["status"] == "Open"
                assert data["credit_note"]["total_value"] == "-120"
                assert data["credit_note"]["credit_note_items"][0]["price"] == "-100"
            if name == "create_credit_note_reconciliation":
                assert data["invoice"]["url"] == BASE + "invoices/7"
                assert data["credit_note_reconciliation"]["gross_value"] == "60"
        assert len([c for c in calls if c[0] == "POST"]) == 2
        assert len([c for c in calls if c[0] == "PUT"]) == 1
        assert not any("send_email" in path for _, path, _ in calls)
        issue_index = next(i for i, call in enumerate(calls) if call[0] == "PUT")
        assert calls[issue_index][1:] == ("credit_notes/8/transitions/mark_as_sent", None)
        assert calls[issue_index + 1][0:2] == ("GET", "credit_notes/8")
        assert "Current-request Draft issuance policy" in files["docs/credit-notes.md"].decode()
        assert "`issue_credit_note`" in skill


def test_credit_package_preserves_provider_remediation_docs_and_source_digests():
    root = Path(__file__).resolve().parents[1]
    files = package_files(root)
    digests = json.loads(files["docs/source-digests.json"])
    for name in ("analysis.md", "credit-notes.md", "agent-rules.md"):
        source = root / "docs" / name
        assert "docs/" + name in files
        assert digests["docs/" + name] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert not (root / "freeagent_ai/analysis.py").exists()
    assert "provider-returned or explicitly user-supplied expected" in files["docs/credit-notes.md"].decode()
