"""Shipped evidence workflows resolve to remote FreeAgent reads, not local engines."""

import hashlib
import json
import re
import time
import urllib.error
from email.message import Message
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
from freeagent_ai.public_tools import Dispatcher

BASE = "https://api.freeagent.com/v2/"
ROOT = Path(__file__).resolve().parents[1]
CASES = [
    (
        "cash-flow",
        "list_bank_accounts",
        {},
        "bank_accounts",
        [{"url": BASE + "bank_accounts/1", "currency": "GBP", "current_balance": "12.34"}],
    ),
    (
        "profitability",
        "get_project",
        {"id": "2"},
        "project",
        {"url": BASE + "projects/2", "budget": "8", "budget_units": "Days", "hours_per_day": "7.5"},
    ),
    (
        "reports",
        "get_profit_and_loss",
        {"from_date": "2026-01-01", "to_date": "2026-03-31"},
        "profit_and_loss_summary",
        {"operating_profit": "23.45"},
    ),
    (
        "tax-overview",
        "get_vat_return",
        {"period_ends_on": "2026-03-31"},
        "vat_return",
        {
            "url": BASE + "vat_returns/2026-03-31",
            "period_ends_on": "2026-03-31",
            "payments": [{"label": "Payment Due", "due_on": "2026-05-07", "amount_due": "120", "status": "unpaid"}],
        },
    ),
]


@pytest.mark.parametrize("skill,tool,args,root,evidence", CASES)
@pytest.mark.parametrize("denied", [False, True])
def test_packaged_workflow_discovery_and_provider_http_read(accounts, skill, tool, args, root, evidence, denied):
    files = package_files(ROOT)
    text = files[f"skills/{skill}/SKILL.md"].decode()
    # Check the workflow itself, not the inventory appended to every skill.
    workflow = text.split("## Hosted transport")[0]
    assert f"`{tool}`" in workflow
    accounts.replace(
        "reviewer", BASE + "company/1", "production", {"access_token": "synthetic", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("reviewer", frozenset({"freeagent:read"}), 101)
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append((method, url))
        assert method == "GET"
        assert url.startswith(BASE)
        if denied:
            raise urllib.error.HTTPError(url, 403, "denied", Message(), None)
        return {root: evidence}, {}

    dispatch = Dispatcher(accounts, "id", "secret", client_factory=lambda *a: HostedClient(*a, transport=transport))
    verifier = SimpleNamespace(principal=lambda _: principal)
    with TestClient(create_app(settings(), accounts, verifier, dispatch), base_url=ORIGIN) as client:
        headers = {"Authorization": "Bearer synthetic", "Accept": "application/json, text/event-stream"}
        discovered = client.post(
            "/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        ).json()["result"]["tools"]
        descriptor = next(t for t in discovered if t["name"] == tool)
        assert descriptor["annotations"]["readOnlyHint"] is True
        response = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": tool, "arguments": args}},
        )
    assert response.status_code == 200
    result = response.json()["result"]
    if denied:
        assert result["isError"] is True
        assert "Read incomplete" in result["content"][0]["text"]
    else:
        assert not result.get("isError", False)
        output = json.loads(result["content"][0]["text"])
        if "collected_at" in descriptor["outputSchema"]["properties"]:
            assert output.pop("collected_at")
        assert output == {root: evidence}
    assert len(calls) == 1
    expected_path = {
        "list_bank_accounts": "bank_accounts",
        "get_project": "projects/2",
        "get_profit_and_loss": "accounting/profit_and_loss/summary",
        "get_vat_return": "vat_returns/2026-03-31",
    }[tool]
    assert urlsplit(calls[0][1]).path == "/v2/" + expected_path


def test_evidence_workflows_package_docs_links_and_no_engine_instructions():
    files = package_files(ROOT)
    digests = json.loads(files["docs/source-digests.json"])
    assert digests["docs/analysis.md"] == hashlib.sha256((ROOT / "docs/analysis.md").read_bytes()).hexdigest()
    for skill in ["cash-flow", "profitability", "reports", "tax-overview"]:
        text = files[f"skills/{skill}/SKILL.md"].decode().split("## Hosted transport")[0]
        assert not re.search(r"freeagent_ai\.analysis|receipt_delay_days|cost_rates|additional:true|Run `|runpy", text)
        for target in re.findall(r"\]\((\.\./\.\./docs/[^)#]+)(?:#[^)]*)?\)", text):
            assert target.removeprefix("../../") in files
    assert "docs/analysis.md" in files
    assert "get_profit_and_loss" in files["docs/analysis.md"].decode()
