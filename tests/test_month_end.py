"""Month-end package -> named tools -> authenticated provider reads; no assistant simulation."""

import hashlib
import json
import time
import urllib.error
from datetime import datetime
from email.message import Message
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import settings
from starlette.testclient import TestClient

from freeagent_ai.hosted_accounts import Principal
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.package_contract import coverage
from freeagent_ai.public_package import package_files
from freeagent_ai.public_tools import Dispatcher

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.freeagent.com/v2/"
CASES = [
    (
        "bank_transactions",
        {"bank_account": "1", "view": "unexplained"},
        {"amount": "-12.30", "unexplained_amount": "-12.30"},
    ),
    ("invoices", {"view": "overdue"}, {"status": "Overdue", "due_value": "12.30", "currency": "GBP"}),
    ("invoices", {"view": "draft"}, {"status": "Draft", "total_value": "-12.30", "currency": "EUR"}),
    ("bills", {"view": "overdue"}, {"status": "Overdue", "due_value": "12.30", "currency": "GBP"}),
    (
        "timeslips",
        {"view": "unbilled"},
        {
            "hours": "1.25",
            "timer": {"running": True, "start_from": "2026-09-15T09:00:00Z"},
            "billed_on_invoice": BASE + "invoices/9",
        },
    ),
    ("expenses", {}, {"gross_value": "-12.30", "currency": "GBP", "receipt_reference": "SYNTH-1"}),
]


@pytest.mark.parametrize("collection,filters,evidence", CASES)
@pytest.mark.parametrize("state", ["records", "empty", "denied", "second-page-denied", "malformed"])
def test_month_end_packaged_reads(accounts, collection, filters, evidence, state):
    files = package_files(ROOT)
    tool = "list_" + collection
    assert tool in {item["name"] for item in coverage(files)["month-end"]["operations"]}
    accounts.replace(
        "month", BASE + "company/1", "production", {"access_token": "synthetic", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("month", frozenset({"freeagent:read"}), 101)
    calls = []
    dated = collection != "invoices"
    arguments = {**filters, **({"from_date": "2026-09-01", "to_date": "2026-09-30"} if dated else {})}
    first = {"url": BASE + collection + "/1", "dated_on": "2026-09-15", **evidence}
    # Exact matching evidence is preserved for human review, never collapsed as a duplicate.
    second = {**first, "url": BASE + collection + "/2"}

    def transport(method, url, deadline, **kwargs):
        assert method == "GET"
        assert url.startswith(BASE + collection)
        query = parse_qs(urlsplit(url).query)
        for name, value in arguments.items():
            expected = BASE + "bank_accounts/1" if name == "bank_account" else value
            assert query[name] == [expected]
        calls.append(url)
        if state == "denied" or (state == "second-page-denied" and len(calls) == 2):
            raise urllib.error.HTTPError(url, 403, "denied", Message(), None)
        if state == "malformed":
            return {collection: None}, {}
        if state == "empty":
            return {collection: []}, {}
        if len(calls) == 1:
            return {collection: [first]}, {"Link": "<" + url + '&page=2>; rel="next"'}
        return {collection: [second]}, {}

    dispatch = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    verifier = SimpleNamespace(principal=lambda _: principal)
    with TestClient(create_app(settings(), accounts, verifier, dispatch), base_url=ORIGIN) as client:
        headers = {"Authorization": "Bearer synthetic", "Accept": "application/json, text/event-stream"}
        discovered = client.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        ).json()["result"]["tools"]
        descriptor = next(item for item in discovered if item["name"] == tool)
        assert descriptor["annotations"]["readOnlyHint"] is True
        assert "collected_at" in descriptor["outputSchema"]["properties"]
        result = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": arguments}},
        ).json()["result"]
    if state in {"denied", "second-page-denied", "malformed"}:
        assert result["isError"] is True
        assert "Read incomplete" in result["content"][0]["text"]
    else:
        assert not result.get("isError", False)
        output = json.loads(result["content"][0]["text"])
        assert output[collection] == ([] if state == "empty" else [first, second])
        offset = datetime.fromisoformat(output["collected_at"]).utcoffset()
        assert offset is not None and offset.total_seconds() == 0
    assert len(calls) == (2 if state in {"records", "second-page-denied"} else 1)


def test_month_end_explanation_and_handoff_contract():
    files = package_files(ROOT)
    workflow = files["skills/month-end/SKILL.md"].decode().split("## Hosted transport")[0]
    for requirement in [
        "read only",
        "current provider status",
        "missing dates",
        "not an atomic",
        "uncertain",
        "separate approval",
        "Existing unrelated records stay unchanged",
        "never blindly",
        "original company",
        "Read failure",
    ]:
        assert requirement.lower() in workflow.lower()
    assert "No invoice date query" in files["docs/month-end.md"].decode()
    digests = json.loads(files["docs/source-digests.json"])
    assert digests["docs/month-end.md"] == hashlib.sha256((ROOT / "docs/month-end.md").read_bytes()).hexdigest()
