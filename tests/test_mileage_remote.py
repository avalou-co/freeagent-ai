"""Provider mileage mechanics through the generated plugin and authenticated HTTP.

Synthetic provider responses are evidence, not locally calculated tax expectations.
"""

import json
import time
import urllib.error
from copy import deepcopy
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
from freeagent_ai.public_package import package_files
from freeagent_ai.public_tools import Dispatcher

BASE = "https://api.freeagent.com/v2/"


def claim_args(**changes):
    return dict(
        user="1",
        dated_on="2026-10-26",
        description="Synthetic site visit",
        mileage="20.125",
        vehicle_type="Car",
        engine_type="Electric (Public charger)",
        engine_size="All",
        reclaim_mileage=1,
        have_vat_receipt=False,
        confirmed=True,
        **changes,
    )


@pytest.fixture
def remote(accounts):
    accounts.replace(
        "mileage", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("mileage", frozenset({"freeagent:read", "freeagent:write"}), 101)
    denied = Principal("mileage", frozenset(), 101)
    calls = []
    state = {
        "failure": None,
        "expense": dict(
            url=BASE + "expenses/12",
            user=BASE + "users/1",
            category="Mileage",
            dated_on="2026-10-26",
            description="Synthetic site visit",
            mileage="20.125",
            vehicle_type="Car",
            engine_type="Electric (Public charger)",
            engine_size="All",
            reclaim_mileage=1,
            have_vat_receipt=False,
            gross_value="-17.23",
            currency="GBP",
            reclaim_mileage_rate="0.173",
            private="hidden",
        ),
    }
    provider_settings = {
        "mileage_rates": [
            {
                "from": "2026-01-01",
                "to": "2026-12-31",
                "value": {"Car": {"basic_rate": "0.173"}, "basic_rate_limit": 123},
            }
        ],
        "engine_type_and_size_options": [],
    }

    def transport(method, url, deadline, **kwargs):
        path = urlsplit(url).path.removeprefix("/v2/")
        calls.append((method, path, deepcopy(kwargs.get("body"))))
        if path.startswith("company"):
            return {"company": {"url": BASE + "company/1"}}, {}
        failure = state["failure"]
        if method == "POST":
            if failure == "timeout":
                raise TimeoutError("uncertain synthetic write")
            if failure == "rejection":
                raise urllib.error.HTTPError(url, 422, "unit or vehicle rejected", Message(), None)
            return {"expense": deepcopy(state["expense"])}, {"Location": BASE + "expenses/12"}
        if failure == "readback" and path == "expenses/12":
            raise urllib.error.HTTPError(url, 503, "unavailable", Message(), None)
        if failure == "lookup":
            raise urllib.error.HTTPError(url, 403, "unavailable", Message(), None)
        if path == "expenses/mileage_settings":
            return {"mileage_settings": deepcopy(provider_settings)}, {}
        if path == "expenses":
            page = parse_qs(urlsplit(url).query).get("page", ["1"])[0]
            return {"expenses": [deepcopy(state["expense"])] if page == "1" else []}, (
                {"Link": f'<{BASE}expenses?page=2&per_page=1>; rel="next"'} if page == "1" else {}
            )
        assert path == "expenses/12"
        return {"expense": deepcopy(state["expense"])}, {}

    dispatcher = Dispatcher(
        accounts, "dummy", "dummy", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    verifier = SimpleNamespace(principal=lambda token: denied if token == "denied" else principal)
    with TestClient(create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN) as client:

        def rpc(method, params, token="allowed"):
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            )
            assert response.status_code == 200
            return response.json()["result"]

        yield rpc, calls, state, provider_settings


def invoke(remote, name, arguments=None, token="allowed"):
    return remote[0]("tools/call", {"name": name, "arguments": arguments or {}}, token)


def test_package_requires_provider_inputs_not_executable_preview():
    root = Path(__file__).resolve().parents[1]
    files = package_files(root)
    skill = files["skills/mileage/SKILL.md"].decode()
    assert "monetary reimbursement preview is unavailable" in skill
    assert "ask for the journey distance in miles" in skill
    assert "Resolve uncertain matches" in skill
    assert "Obtain approval for this exact plan" in " ".join(skill.split())
    assert not (root / ".agents/skills/mileage/scripts/preview.py").exists()
    assert not any(path.endswith(".py") for path in files)
    digests = json.loads(files["docs/source-digests.json"])
    assert not any("preview.py" in path for path in digests)


def test_packaged_discovered_settings_duplicate_reads_and_provider_calculated_create(remote):
    tools = {tool["name"]: tool for tool in remote[0]("tools/list", {})["tools"]}
    for name in (
        "get_company",
        "list_users",
        "get_mileage_settings",
        "list_expenses",
        "get_expense",
        "create_mileage_expense",
    ):
        assert name in tools
    assert not any("calculate" in name or "preview" in name for name in tools)
    settings_result = invoke(remote, "get_mileage_settings")
    assert settings_result["structuredContent"]["mileage_settings"] == remote[3]
    history = invoke(remote, "list_expenses", {"from_date": "2026-10-01", "to_date": "2026-10-26", "per_page": 1})
    assert len(history["structuredContent"]["expenses"]) == 1
    # Duplicate dispositions and approval belong to the agent; this tests the mechanics after a reviewed decision.
    result = invoke(remote, "create_mileage_expense", claim_args())
    assert not result.get("isError", False)
    expense = result["structuredContent"]["expense"]
    assert expense["gross_value"] == "-17.23"
    assert expense["reclaim_mileage_rate"] == "0.173"
    assert expense["mileage"] == "20.125"
    assert "private" not in expense
    writes = [call for call in remote[1] if call[0] == "POST"]
    assert len(writes) == 1
    submitted = writes[0][2]["expense"]
    assert submitted["mileage"] == "20.125"
    assert submitted["user"] == BASE + "users/1"
    assert "gross_value" not in submitted and "reclaim_mileage_rate" not in submitted
    assert remote[1][-1][:2] == ("GET", "expenses/12")


@pytest.mark.parametrize("failure", ["timeout", "rejection", "readback"])
def test_failed_provider_write_or_readback_is_not_replayed(remote, failure):
    remote[2]["failure"] = failure
    result = invoke(remote, "create_mileage_expense", claim_args())
    assert result.get("isError")
    assert len([call for call in remote[1] if call[0] == "POST"]) == 1


@pytest.mark.parametrize("case", ["refused", "missing", "unit", "permission"])
def test_refusal_missing_input_unsupported_unit_and_denied_access_do_not_write(remote, case):
    args = claim_args()
    token = "allowed"
    if case == "refused":
        args["confirmed"] = False
    elif case == "missing":
        args.pop("mileage")
    elif case == "unit":
        args["unit"] = "km"  # Not part of the documented input shape: never silently convert.
    else:
        token = "denied"
    result = invoke(remote, "create_mileage_expense", args, token)
    assert result.get("isError")
    assert not remote[1]


def test_provider_missing_fields_remain_absent_and_lookup_failure_is_not_empty_history(remote):
    remote[2]["expense"].pop("gross_value")
    remote[2]["expense"].pop("reclaim_mileage_rate")
    expense = invoke(remote, "get_expense", {"id": "12"})["structuredContent"]["expense"]
    assert "gross_value" not in expense and "reclaim_mileage_rate" not in expense
    remote[2]["failure"] = "lookup"
    result = invoke(remote, "list_expenses")
    assert result.get("isError")
    assert not any(method == "POST" for method, _, _ in remote[1])


def test_provider_decides_invalid_distance_without_local_conversion(remote):
    remote[2]["failure"] = "rejection"
    args = claim_args()
    args["mileage"] = "20 km"
    result = invoke(remote, "create_mileage_expense", args)
    assert result.get("isError")
    write = next(call for call in remote[1] if call[0] == "POST")
    assert write[2]["expense"]["mileage"] == "20 km"
    assert "422" in result["content"][0]["text"]
