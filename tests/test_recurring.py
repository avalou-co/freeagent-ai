"""Packaged recurring workflow -> authenticated HTTP MCP -> provider reads only."""

import json
import time
import urllib.error
from copy import deepcopy
from datetime import datetime, timezone
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

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


def profile(identifier="1", **overrides) -> dict[str, Any]:
    return {
        "url": BASE + "recurring_invoices/" + identifier,
        "contact": BASE + "contacts/7",
        "project": BASE + "projects/9",
        "reference": "SYNTHETIC-" + identifier,
        "frequency": "Monthly",
        "recurring_status": "Active",
        "next_recurs_on": "2026-01-31",
        "recurring_end_date": "",
        "currency": "GBP",
        "net_value": "100",
        "sales_tax_value": "20",
        "total_value": "120",
        "payment_terms_in_days": 30,
        "invoice_items": [dict(description="Synthetic service", quantity="1", price="100", private="hidden")],
        "private": "hidden",
        **overrides,
    }


@pytest.fixture
def remote(accounts):
    accounts.replace(
        "recurring", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("recurring", frozenset({"freeagent:read"}), 101)
    denied = Principal("recurring", frozenset({"freeagent:write"}), 101)
    verifier = SimpleNamespace(principal=lambda token: principal if token == "read" else denied)
    rows = {
        "active": [profile(), profile("2", currency="EUR", total_value="-42.75", frequency="Annually")],
        # Inactive is a provider view, not an invented status string.
        "inactive": [profile("3", recurring_end_date="2025-12-31")],
        "draft": [profile("4", recurring_status="Draft")],
    }
    calls = []
    failure: list[Any] = []

    def transport(method, url, deadline, **kwargs):
        assert method == "GET", "Recurring workflow must never mutate provider records"
        calls.append(url)
        if failure:
            if isinstance(failure[0], int):
                raise urllib.error.HTTPError(url, failure[0], "denied", Message(), None)
            if failure[0] == "malformed":
                return {"recurring_invoices": ["invalid-record"]}, {}
            return {"wrong_root": []}, {}
        parsed = urlsplit(url)
        if parsed.path != "/v2/recurring_invoices":
            identifier = parsed.path.rsplit("/", 1)[-1]
            found = next(row for group in rows.values() for row in group if row["url"].endswith("/" + identifier))
            return {"recurring_invoice": deepcopy(found)}, {}
        query = parse_qs(parsed.query)
        view = query.get("view", ["active"])[0]
        page = int(query.get("page", ["1"])[0])
        selected = rows[view]
        next_query = {"view": view, "contact": query.get("contact", [""])[0], "page": 2, "per_page": 1}
        headers = (
            {"Link": f'<{BASE}recurring_invoices?{urlencode(next_query)}>; rel="next"'}
            if page == 1 and len(selected) > 1
            else {}
        )
        return {"recurring_invoices": deepcopy(selected[:1] if page == 1 else selected[1:])}, headers

    dispatcher = Dispatcher(
        accounts, "dummy", "dummy", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    with TestClient(create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN) as client:

        def rpc(method, params, token="read"):
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
            assert response.status_code == 200
            return response.json()["result"]

        yield rpc, rows, calls, failure


def check_timestamp(value):
    timestamp = datetime.fromisoformat(value)
    assert timestamp.tzinfo == timezone.utc
    assert (datetime.now(timezone.utc) - timestamp).total_seconds() < 30


def test_packaged_skill_discovery_and_actual_named_remote_profile_reads(remote):
    rpc, _, calls, _ = remote
    root = Path(__file__).resolve().parents[1]
    files = package_files(root)
    skill = files["skills/recurring-revenue/SKILL.md"].decode()
    assert "Call `list_recurring_invoices`" in skill
    assert "with `get_recurring_invoice`" in skill
    descriptors = {tool["name"]: tool for tool in rpc("tools/list", {})["tools"]}
    audit = {tool["name"]: tool for tool in json.loads(files["docs/public-tool-audit.json"])}
    for name in ("list_recurring_invoices", "get_recurring_invoice"):
        assert descriptors[name]["inputSchema"] == audit[name]["inputSchema"]
        assert descriptors[name]["annotations"]["readOnlyHint"]
        assert descriptors[name]["securitySchemes"] == [{"type": "oauth2", "scopes": ["freeagent:read"]}]
    assert "docs/recurring-revenue.md" in json.loads(files["docs/source-digests.json"])
    for view, identifiers in [("active", ["1", "2"]), ("inactive", ["3"]), ("draft", ["4"])]:
        result = rpc("tools/call", dict(name="list_recurring_invoices", arguments={"view": view, "contact": "7"}))
        assert not result["isError"]
        output = result["structuredContent"]
        assert [row["url"] for row in output["recurring_invoices"]] == [
            BASE + "recurring_invoices/" + i for i in identifiers
        ]
        check_timestamp(output["collected_at"])
    first_query = parse_qs(urlsplit(calls[0]).query)
    assert first_query["contact"] == [BASE + "contacts/7"]
    assert first_query["view"] == ["active"]
    assert len(calls) == 4  # Two active pages, then inactive and draft.
    detail = rpc("tools/call", dict(name="get_recurring_invoice", arguments={"id": "1"}))["structuredContent"]
    assert calls[-1] == BASE + "recurring_invoices/1"
    check_timestamp(detail["collected_at"])
    row = detail["recurring_invoice"]
    assert row["next_recurs_on"] == "2026-01-31"
    assert row["recurring_end_date"] == ""
    assert row["project"] == BASE + "projects/9"
    assert row["invoice_items"] == [dict(description="Synthetic service", quantity="1", price="100")]
    assert "private" not in row


def test_provider_values_currencies_and_missing_fields_not_synthesized(remote):
    rpc, rows, _, _ = remote
    for key in ("next_recurs_on", "recurring_end_date", "currency", "total_value", "recurring_status"):
        rows["active"][0].pop(key)
    output = rpc("tools/call", dict(name="list_recurring_invoices", arguments={"view": "active"}))["structuredContent"]
    first, second = output["recurring_invoices"]
    assert not {"next_recurs_on", "recurring_end_date", "currency", "total_value", "recurring_status"} & first.keys()
    assert second["currency"] == "EUR"
    assert second["total_value"] == "-42.75"
    assert second["frequency"] == "Annually"
    assert set(output) == {"recurring_invoices", "collected_at"}
    assert not {"events", "commitments", "expected_receipt_date", "forecast"} & second.keys()


def test_successful_empty_collection_differs_from_unavailable_read(remote):
    rpc, rows, _, _ = remote
    rows["active"] = []
    output = rpc("tools/call", dict(name="list_recurring_invoices", arguments={"view": "active"}))
    assert not output["isError"]
    assert output["structuredContent"]["recurring_invoices"] == []
    check_timestamp(output["structuredContent"]["collected_at"])


@pytest.mark.parametrize("failure_mode", [403, 404, 422, 500, "malformed", "missing_root"])
def test_denied_malformed_and_provider_errors_are_incomplete_not_empty(remote, failure_mode):
    rpc, _, _, failure = remote
    failure.append(failure_mode)
    result = rpc("tools/call", dict(name="list_recurring_invoices", arguments={"view": "active"}))
    assert result["isError"]
    assert "Read incomplete" in result["content"][0]["text"]
    assert not result.get("structuredContent")


def test_read_scope_and_fixed_id_boundary_precede_provider(remote):
    rpc, _, calls, _ = remote
    denied = rpc("tools/call", dict(name="get_recurring_invoice", arguments={"id": "1"}), token="write-only")
    assert denied["isError"]
    assert "scope" in denied["content"][0]["text"]
    invalid = rpc("tools/call", dict(name="get_recurring_invoice", arguments={"id": "../company"}))
    assert invalid["isError"]
    assert calls == []


def test_recurring_surface_has_only_provider_reads_without_custom_engine():
    root = Path(__file__).resolve().parents[1]
    assert not (root / "freeagent_ai/recurring.py").exists()
    recurring = {name: op for name, op in REGISTRY.items() if "recurring" in name}
    assert set(recurring) == {"list_recurring_invoices", "get_recurring_invoice"}
    assert {op.method for op in recurring.values()} == {"GET"}
    assert {op.endpoint for op in recurring.values()} == {"recurring_invoices", "recurring_invoices/{id}"}
    files = package_files(root)
    assert not any("recurring" in name and name.endswith(".py") for name in files)
    for name in ("skills/recurring-revenue/SKILL.md", "docs/recurring-revenue.md"):
        text = files[name].decode()
        assert "recurring_scenario" not in text
        assert "billing_dates" not in text
        assert "freeagent_ai.recurring" not in text
    assert not any(name.startswith("calculate_") for name in recurring)
