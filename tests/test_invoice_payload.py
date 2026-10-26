"""Invoice workflow -> remote MCP -> provider payload/readback, without accounting math."""

import json
import time
import urllib.error
from copy import deepcopy
from email.message import Message
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import settings
from starlette.testclient import TestClient

from freeagent_ai import mcp_server
from freeagent_ai.hosted_accounts import Principal
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.public_package import package_files
from freeagent_ai.public_tools import Dispatcher

BASE = "https://api.freeagent.com/v2/"


def invoice():
    return {
        "contact": BASE + "contacts/7",
        "project": BASE + "projects/8",
        "dated_on": "2026-10-26",
        "payment_terms_in_days": 0,
        "currency": "EUR",
        "exchange_rate": "0.91",
        "reference": "",
        "invoice_items": [
            {
                "description": "Synthetic approved service",
                "item_type": "Services",
                "quantity": "2.50",
                "price": "17.83",
                "sales_tax_rate": "0",
                "second_sales_tax_rate": "7.5",
                "sales_tax_status": "TAXABLE",
                "second_sales_tax_status": "EXEMPT",
                "category": BASE + "categories/001",
                "stock_item": BASE + "stock_items/3",
            }
        ],
    }


@pytest.fixture
def remote(accounts):
    accounts.replace(
        "invoice", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("invoice", frozenset({"freeagent:read", "freeagent:write"}), 101)
    read_only = Principal("invoice", frozenset({"freeagent:read"}), 101)
    calls = []
    state: dict[str, Any] = {"failure": None, "posted": None}
    sources = {
        "contacts": [{"url": BASE + "contacts/7", "organisation_name": "Synthetic Client"}],
        "projects": [{"url": BASE + "projects/8", "contact": BASE + "contacts/7", "currency": "EUR"}],
        "estimates": [
            {
                "url": BASE + "estimates/9",
                "project": BASE + "projects/8",
                "status": "Approved",
                "currency": "EUR",
                "estimate_items": invoice()["invoice_items"],
            }
        ],
        "expenses": [
            {
                "url": BASE + "expenses/10",
                "project": BASE + "projects/8",
                "gross_value": "-9.10",
                "rebill_to_project": BASE + "projects/8",
                "rebilled_on_invoice": BASE + "invoices/2",
            }
        ],
        "bills": [
            {
                "url": BASE + "bills/11",
                "project": BASE + "projects/8",
                "rebill_to_project": BASE + "projects/8",
                "total_value": "72.15",
                "rebilled_on_invoice_item": BASE + "invoices/2",
                "exchange_rate": "1.2",
            }
        ],
        "timeslips": [
            {
                "url": BASE + "timeslips/12",
                "project": BASE + "projects/8",
                "hours": "2",
                "billed_on_invoice": BASE + "invoices/2",
            }
        ],
        "invoices": [{"url": BASE + "invoices/2", "status": "Draft", "currency": "EUR"}],
        "bank_transactions": [],
        "bank_transaction_explanations": [
            {
                "url": BASE + "bank_transaction_explanations/13",
                "project": BASE + "projects/8",
                "gross_value": "-7.20",
                "rebill_type": "cost",
                "sales_tax_value": "-1.20",
            }
        ],
    }

    def transport(method, url, deadline, **kwargs):
        parsed = urlsplit(url)
        path = parsed.path.removeprefix("/v2/")
        calls.append((method, path, deepcopy(kwargs.get("body")), parsed.query))
        if method == "POST":
            assert path == "invoices", "No issuing or sending endpoint is permitted"
            if state["failure"] == "reject":
                raise urllib.error.HTTPError(
                    url, 422, "invalid", Message(), BytesIO(b'{"errors":{"source":"already billed"}}')
                )
            if state["failure"] == "timeout":
                raise TimeoutError("uncertain write")
            state["posted"] = deepcopy(kwargs["body"]["invoice"])
            return {"invoice": {"url": BASE + "invoices/91"}}, {"Location": BASE + "invoices/91"}
        if path.startswith("company"):
            return {"company": {"url": BASE + "company/1"}}, {}
        if path == "invoices/91":
            if state["failure"] == "readback":
                raise urllib.error.HTTPError(url, 503, "unavailable", Message(), None)
            row = {
                **state["posted"],
                "url": BASE + path,
                "net_value": "provider-net",
                "total_value": "provider-total",
                "second_sales_tax_value": "provider-second-tax",
            }
            if state["failure"] == "unexpected":
                row["invoice_items"] = [
                    {
                        "url": BASE + "invoice_items/99",
                        "description": "Unexpected provider source",
                        "bill": BASE + "bills/66",
                    }
                ]
            if state["failure"] == "missing":
                row.pop("currency")
                row.pop("total_value")
            return {"invoice": row}, {}
        resource, _, identifier = path.partition("/")
        if state["failure"] == "lookup":
            raise urllib.error.HTTPError(url, 403, "denied", Message(), None)
        rows = sources[resource]
        if identifier:
            return {resource[:-1]: deepcopy(rows[0])}, {}
        query = parse_qs(parsed.query)
        if resource == "expenses" and query.get("page") != ["2"]:
            return {"expenses": []}, {"Link": f'<{BASE}expenses?project={BASE}projects/8&page=2>; rel="next"'}
        return {resource: deepcopy(rows)}, {}

    dispatcher = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    verifier = SimpleNamespace(principal=lambda token: read_only if token == "read" else principal)
    with TestClient(create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN) as client:

        def rpc(method, params, token="write"):
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
            assert response.status_code == 200
            return response.json()["result"]

        yield rpc, calls, state


def create(rpc, payload, confirmed=True, token="write"):
    return rpc(
        "tools/call",
        {"name": "create_draft_invoice_from_payload", "arguments": {"invoice": payload, "confirmed": confirmed}},
        token,
    )


def test_packaged_named_workflow_reads_and_exact_manual_invoice(remote):
    rpc, calls, _ = remote
    files = package_files(Path(__file__).resolve().parents[1])
    skill = files["skills/invoicing/SKILL.md"].decode()
    assert "create_draft_invoice_from_payload" in skill
    assert "find_contacts" not in skill
    assert "`POST invoices`" not in skill
    assert "Do not send" in skill
    assert "docs/invoicing.md" in json.loads(files["docs/source-digests.json"])
    tools = {tool["name"]: tool for tool in rpc("tools/list", {})["tools"]}
    descriptor = tools["create_draft_invoice_from_payload"]
    assert descriptor["inputSchema"]["properties"]["invoice"]["type"] == "object"
    assert descriptor["securitySchemes"] == [{"type": "oauth2", "scopes": ["freeagent:write"]}]
    audit = {tool["name"]: tool for tool in json.loads(files["docs/public-tool-audit.json"])}
    assert audit["create_draft_invoice_from_payload"]["inputSchema"] == descriptor["inputSchema"]
    for resource, args in [
        ("contacts", {}),
        ("projects", {"contact": "7"}),
        ("estimates", {"project": "8"}),
        ("expenses", {"project": "8"}),
        ("bills", {}),
        ("timeslips", {"project": "8"}),
        ("invoices", {"project": "8"}),
    ]:
        result = rpc("tools/call", {"name": "list_" + resource, "arguments": args})
        assert not result["isError"]
        assert resource in result["structuredContent"]
    assert len([c for c in calls if c[1] == "expenses"]) == 2
    payload = invoice()
    original = deepcopy(payload)
    result = create(rpc, payload)
    assert not result["isError"]
    expected = {
        **original,
        "status": "Draft",
        "send_new_invoice_emails": False,
        "send_reminder_emails": False,
        "send_thank_you_emails": False,
    }
    assert [c[:3] for c in calls if c[0] == "POST"] == [("POST", "invoices", {"invoice": expected})]
    assert payload == original
    actual = result["structuredContent"]["invoice"]
    assert actual["invoice_items"] == original["invoice_items"]
    assert actual["total_value"] == "provider-total"
    assert actual["second_sales_tax_value"] == "provider-second-tax"
    assert actual["currency"] == "EUR"


@pytest.mark.parametrize(
    "includes",
    [
        {
            "include_timeslips": "billed_grouped_by_timeslip",
            "include_estimates": "billed_grouped_by_estimate",
            "include_expenses": "billed_grouped_by_expense",
        },
        {
            "include_timeslips": None,
            "include_estimates": "billed_grouped_by_single_estimate",
            "include_expenses": "billed_grouped_by_single_expense",
        },
        {"include_estimates": "provider decides invalid mode", "include_expenses": ""},
    ],
)
def test_provider_inclusion_modes_pass_without_local_eligibility_or_billing_logic(remote, includes):
    rpc, calls, _ = remote
    payload = {**invoice(), **includes}
    payload.pop("invoice_items")
    result = create(rpc, payload)
    assert not result["isError"]
    posted = next(c[2]["invoice"] for c in calls if c[0] == "POST")
    assert "invoice_items" not in posted
    for key, value in includes.items():
        assert posted[key] == value


@pytest.mark.parametrize("failure", ["reject", "timeout", "readback"])
def test_provider_rejection_uncertain_creation_and_readback_never_replayed(remote, failure):
    rpc, calls, state = remote
    state["failure"] = failure
    result = create(rpc, invoice())
    assert result["isError"]
    assert len([c for c in calls if c[0] == "POST"]) == 1
    if failure == "readback":
        assert "invoices/91" in str(result)


@pytest.mark.parametrize("confirmed,token", [(False, "write"), (True, "read")])
def test_refused_approval_or_write_scope_denial_never_reaches_provider(remote, confirmed, token):
    rpc, calls, _ = remote
    assert create(rpc, invoice(), confirmed, token)["isError"]
    assert calls == []


@pytest.mark.parametrize("failure", ["missing", "unexpected"])
def test_readback_evidence_is_not_fabricated_or_reconciled_with_custom_math(remote, failure):
    rpc, _, state = remote
    state["failure"] = failure
    result = create(rpc, invoice())["structuredContent"]["invoice"]
    if failure == "missing":
        assert "currency" not in result
        assert "total_value" not in result
    else:
        assert result["invoice_items"][0]["bill"] == BASE + "bills/66"
        assert result["invoice_items"][0]["description"] == "Unexpected provider source"


def test_incomplete_source_lookup_does_not_become_empty_success(remote):
    rpc, calls, state = remote
    state["failure"] = "lookup"
    result = rpc("tools/call", {"name": "list_estimates", "arguments": {"project": "8"}})
    assert result["isError"]
    assert not any(c[0] == "POST" for c in calls)


def test_draft_and_email_defaults_cannot_be_changed_by_exact_payload(remote):
    rpc, calls, _ = remote
    result = create(
        rpc,
        {
            **invoice(),
            "status": "Open",
            "send_new_invoice_emails": True,
            "send_reminder_emails": True,
            "send_thank_you_emails": True,
        },
    )
    assert not result["isError"]
    posted = next(c[2]["invoice"] for c in calls if c[0] == "POST")
    assert posted["status"] == "Draft"
    assert not posted["send_new_invoice_emails"]
    assert not posted["send_reminder_emails"]
    assert not posted["send_thank_you_emails"]


def test_local_payload_wrapper_matches_remote_intent_defaults(monkeypatch):
    calls = []
    monkeypatch.setattr(mcp_server, "_create_and_readback", lambda *args: calls.append(args) or {"invoice": args[-1]})
    payload = invoice()
    mcp_server.create_draft_invoice_from_payload(payload)
    assert calls[0][:2] == ("invoices", "invoice")
    assert calls[0][2]["invoice_items"] == payload["invoice_items"]
    assert calls[0][2]["payment_terms_in_days"] == 0


def test_manual_contact_invoice_does_not_require_project(remote):
    rpc, calls, _ = remote
    payload = invoice()
    payload.pop("project")
    assert not create(rpc, payload)["isError"]
    assert "project" not in next(c[2]["invoice"] for c in calls if c[0] == "POST")


@pytest.mark.parametrize("payload", [[], "not an object"])
def test_malformed_payload_never_reaches_provider(remote, payload):
    rpc, calls, _ = remote
    assert create(rpc, payload)["isError"]
    assert calls == []


def test_explicitly_approved_mixed_manual_and_provider_sources_are_not_rewritten(remote):
    rpc, calls, _ = remote
    payload = {
        **invoice(),
        "include_timeslips": "billed_grouped_by_timeslip",
        "include_estimates": "billed_grouped_by_estimate",
        "include_expenses": "billed_grouped_by_expense",
    }
    assert not create(rpc, payload)["isError"]
    posted = next(c[2]["invoice"] for c in calls if c[0] == "POST")
    assert posted["invoice_items"] == payload["invoice_items"]
    assert posted["include_estimates"] == payload["include_estimates"]
    assert posted["include_expenses"] == payload["include_expenses"]
    assert posted["include_timeslips"] == payload["include_timeslips"]


def test_source_detail_rebilling_and_tax_evidence_survives_remote_projection(remote):
    rpc, _, _ = remote
    bill = rpc("tools/call", {"name": "get_bill", "arguments": {"id": "11"}})["structuredContent"]["bill"]
    assert bill["rebilled_on_invoice_item"] == BASE + "invoices/2"
    assert bill["exchange_rate"] == "1.2"
    expense = rpc("tools/call", {"name": "get_expense", "arguments": {"id": "10"}})["structuredContent"]["expense"]
    assert expense["rebilled_on_invoice"] == BASE + "invoices/2"
    explanation = rpc("tools/call", {"name": "get_bank_transaction_explanation", "arguments": {"id": "13"}})[
        "structuredContent"
    ]["bank_transaction_explanation"]
    assert explanation["project"] == BASE + "projects/8"
    assert explanation["rebill_type"] == "cost"
    assert explanation["sales_tax_value"] == "-1.20"
