"""Synthetic payroll evidence through authenticated hosted MCP HTTP."""

import io
import json
import time
import urllib.error
from copy import deepcopy
from email.message import Message
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from conftest import settings
from starlette.testclient import TestClient

from freeagent_ai.hosted_accounts import Principal
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.package_contract import validate_contract
from freeagent_ai.public_package import ORIGIN, package_files
from freeagent_ai.public_tools import REGISTRY, Dispatcher

BASE = "https://api.freeagent.com/v2/"


@pytest.fixture
def payroll(accounts):
    accounts.replace(
        "payroll", BASE + "company/1", "production", {"access_token": "synthetic", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("payroll", frozenset({"freeagent:read"}), 101)
    denied = Principal("payroll", frozenset(), 101)
    unlinked = Principal("other", frozenset({"freeagent:read"}), 101)
    row = {
        "url": BASE + "payroll/2026/0",
        "period": 0,
        "frequency": "Monthly",
        "dated_on": "2025-04-25",
        "status": "partially_filed",
        "employment_allowance_amount": "0.0",
        "payslips": [{"user": BASE + "users/9", "tax_code": "PRIVATE", "basic_pay": "SECRET"}],
        "private": "PRIVATE",
    }
    payload = {
        "periods": [row],
        "payments": [
            {"due_on": "2025-05-22", "amount_due": "-20.00", "status": "marked_as_paid", "private": "PRIVATE"}
        ],
    }
    mode, calls = [], []

    def transport(method, url, deadline, **kwargs):
        calls.append((method, url))
        assert method == "GET"
        path = urlsplit(url).path
        if mode and isinstance(mode[0], int):
            raise urllib.error.HTTPError(
                url, mode[0], "unavailable", Message(), io.BytesIO(b'{"errors":[{"message":"PRIVATE SECRET"}]}')
            )
        if mode and mode[0] == "malformed":
            return {"periods": None, "payments": []}, {}
        if mode and mode[0] == "missing":
            return {"periods": []}, {}
        if mode and mode[0] == "empty":
            return {"periods": [], "payments": []}, {}
        if path.endswith("/0"):
            return {"period": deepcopy(row)}, {}
        if mode and mode[0] == "pages":
            second = bool(urlsplit(url).query)
            headers = {} if second else {"Link": f'<{BASE}payroll/2026?page=2>; rel="next"'}
            result = deepcopy(payload)
            if second:
                result["periods"][0].update(period=1, status="rejected")
                result["payments"][0] = {"amount_due": "0"}
            return result, headers
        return deepcopy(payload), {}

    dispatcher = Dispatcher(accounts, "id", "secret", client_factory=lambda *a: HostedClient(*a, transport=transport))
    verifier = SimpleNamespace(principal=lambda token: {"denied": denied, "other": unlinked}.get(token, principal))
    with TestClient(create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN) as client:

        def rpc(method, params=None, token="synthetic"):
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            )
            assert response.status_code == 200
            return response.json()["result"]

        yield rpc, payload, mode, calls


def call(rpc, name="list_payroll_periods", arguments=None, token="synthetic"):
    return rpc("tools/call", {"name": name, "arguments": arguments or {"year": "2026"}}, token)


def test_discovery_package_and_faithful_private_projection(payroll):
    from pathlib import Path

    rpc, _, _, calls = payroll
    tools = {t["name"]: t for t in rpc("tools/list")["tools"]}
    files = package_files(Path(__file__).resolve().parents[1])
    contract = validate_contract(files)["payroll"]
    assert set(contract["required_operations"]) == {"list_payroll_periods", "get_payroll_period"}
    for name in contract["required_operations"]:
        assert tools[name]["annotations"]["readOnlyHint"] is True
        assert REGISTRY[name].method == "GET"
    result = call(rpc)
    assert not result.get("isError")
    data = result["structuredContent"]
    assert data["periods"][0]["status"] == "partially_filed"
    assert data["payments"] == [{"due_on": "2025-05-22", "amount_due": "-20.00", "status": "marked_as_paid"}]
    assert data["source_url"] == BASE + "payroll/2026"
    assert data["collected_at"].endswith("+00:00")
    assert "PRIVATE" not in json.dumps(result) and "SECRET" not in json.dumps(result)
    detail = call(rpc, "get_payroll_period", {"year": "2026", "period": "0"})
    assert detail["structuredContent"]["period"]["period"] == 0
    assert "payslips" not in json.dumps(detail)
    assert calls == [("GET", BASE + "payroll/2026"), ("GET", BASE + "payroll/2026/0")]


def test_pages_and_absent_payment_fields_preserved(payroll):
    rpc, _, mode, calls = payroll
    mode.append("pages")
    data = call(rpc)["structuredContent"]
    assert [r["status"] for r in data["periods"]] == ["partially_filed", "rejected"]
    assert data["payments"][1] == {"amount_due": "0"}
    assert len(calls) == 2


@pytest.mark.parametrize("state", ["missing", "malformed", 403, 404])
def test_incomplete_denied_unsupported_is_not_clean(payroll, state):
    rpc, _, mode, _ = payroll
    mode.append(state)
    result = call(rpc)
    assert result["isError"] is True
    assert "structuredContent" not in result
    assert "PRIVATE" not in json.dumps(result) and "SECRET" not in json.dumps(result)


def test_empty_success_and_missing_values_are_distinct(payroll):
    rpc, payload, mode, _ = payroll
    payload["payments"] = [{}]
    assert call(rpc)["structuredContent"]["payments"] == [{}]
    mode.append("empty")
    assert call(rpc)["structuredContent"]["periods"] == []


@pytest.mark.parametrize("token", ["denied", "other"])
def test_scope_and_company_binding_deny_before_provider(payroll, token):
    rpc, _, _, calls = payroll
    assert call(rpc, token=token)["isError"] is True
    assert calls == []


@pytest.mark.parametrize(
    "args",
    [
        {"year": "2026/../company"},
        {"year": "2026", "period": "0/payments/x/mark_as_unpaid"},
        {"year": "2026", "body": {}},
        {"year": "2026", "url": "https://example.invalid"},
    ],
)
def test_fixed_routes_no_mutating_get_or_arbitrary_payload(payroll, args):
    rpc, _, _, calls = payroll
    name = "get_payroll_period" if "period" in args else "list_payroll_periods"
    assert call(rpc, name, args)["isError"] is True
    assert calls == []


@pytest.mark.parametrize("status", ["unfiled", "pending", "rejected", "partially_filed", "filed"])
def test_provider_filing_states_remain_distinct(payroll, status):
    rpc, payload, _, _ = payroll
    payload["periods"][0]["status"] = status
    assert call(rpc)["structuredContent"]["periods"][0]["status"] == status


@pytest.mark.parametrize(
    "collection,value",
    [("periods", [None]), ("payments", [None]), ("payments", [{"amount_due": {"private": "SECRET"}}])],
)
def test_malformed_records_fail_without_private_payload(payroll, collection, value):
    rpc, payload, _, _ = payroll
    payload[collection] = value
    result = call(rpc)
    assert result["isError"] is True
    assert "SECRET" not in json.dumps(result)
