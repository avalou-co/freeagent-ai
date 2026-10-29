"""Real package/discovery/HTTP/provider execution plus audited negative regressions.

Fixture calls prove transport reachability, not assistant behavior, provider tax
rules, file ownership on the host platform or actual marketplace installation.
"""

import base64
import hashlib
import json
import time
import urllib.error
from copy import deepcopy
from dataclasses import replace
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
from freeagent_ai.package_contract import SKILLS, coverage, validate_contract, validate_operations, validate_workflow
from freeagent_ai.public_package import package_files, render_hosted
from freeagent_ai.public_tools import REGISTRY, RESOURCES, TAX_RETURNS, Dispatcher

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://api.freeagent.com/v2/"


def sample_args(op):
    def value(key, schema):
        if key == "year":
            return "2026"
        if key in {"dated_on", "due_on", "from_date", "to_date", "as_at_date", "period_ends_on"}:
            return "2026-01-01"
        kind = schema.get("type")
        if kind == "boolean":
            return True
        if kind == "integer":
            return 1
        if kind == "number":
            return 1
        if kind == "object":
            return {k: value(k, schema["properties"][k]) for k in schema.get("required", [])}
        if kind == "array":
            return []
        return "1"

    schema = op.descriptor.input_schema
    args = {key: value(key, schema["properties"][key]) for key in schema.get("required", [])}
    for key in ("expense", "invoice"):
        if key in args and isinstance(args[key], dict):
            args[key] = {"contact": BASE + "contacts/1", "dated_on": "2026-01-01", "currency": "GBP"}
    if "file" in args:
        args["file"] = {"download_url": "https://files.example.invalid/receipt", "file_id": "synthetic"}
    return args


def provider_result(path):
    path = path.split("?", 1)[0].removeprefix("/v2/")
    record = {"url": BASE + path, "currency": "GBP", "total_value": "-123.45", "description": "Synthetic"}
    if path.endswith("/pdf"):
        return {"pdf": {"content": base64.b64encode(b"%PDF-1.4\nsynthetic\n%%EOF").decode()}}
    if path == "expenses/mileage_settings":
        return {"mileage_settings": {"engine_type_and_size_options": [], "mileage_rates": []}}
    if path == "categories":
        return {
            group: [{"url": BASE + f"categories/{index}", "description": group, "nominal_code": str(index)}]
            for index, group in enumerate(
                ("admin_expenses_categories", "cost_of_sales_categories", "income_categories", "general_categories"), 1
            )
        }
    if path.startswith("payroll/"):
        return {"period": record} if len(path.split("/")) == 3 else {"periods": [record], "payments": []}
    if path == "company":
        return {"company": {"url": BASE + "company", "currency": "GBP"}}
    if path == "users/me":
        return {"user": {"url": BASE + "users/1"}}
    for endpoint, root in TAX_RETURNS.items():
        endpoint = endpoint.replace("{user_id}", "1")
        if path == endpoint:
            return {root + "s": [record]}
        if path.startswith(endpoint + "/"):
            return {root: record}
    for endpoint, (root, _) in RESOURCES.items():
        if path == endpoint:
            return {endpoint: [record]}
        if path.startswith(endpoint + "/"):
            return {root: record}
    if path.startswith("accounting/"):
        root = {
            "accounting/profit_and_loss/summary": "profit_and_loss_summary",
            "accounting/balance_sheet": "balance_sheet",
            "accounting/trial_balance/summary": "trial_balance_summary",
        }[path]
        evidence = {"total": "-123.45"}
        return {root: [evidence] if root == "trial_balance_summary" else evidence}
    if path.endswith("/attachments"):
        return {"attachments": [{"url": BASE + "attachments/1", "file_name": "synthetic.pdf", "file_size": 5}]}
    if path.startswith("bank_transaction_explanations/"):
        return {"bank_transaction_explanation": record}
    raise AssertionError(f"Uncovered provider fixture path: {path}")


@pytest.fixture
def remote(accounts, monkeypatch):
    accounts.replace(
        "contract", BASE + "company/1", "production", {"access_token": "synthetic", "expires_at": time.time() + 3600}, 0
    )
    read_write = Principal("contract", frozenset({"freeagent:read", "freeagent:write"}), 101)
    denied = Principal("contract", frozenset(), 101)
    calls, mode = [], []

    def transport(method, url, deadline, **kwargs):
        assert url.startswith(BASE)
        calls.append((method, url, kwargs.get("body")))
        if mode and mode[0] == "denied":
            raise urllib.error.HTTPError(url, 403, "denied", Message(), None)
        if mode and mode[0] == "readback" and method == "GET":
            raise urllib.error.HTTPError(url, 503, "unavailable", Message(), None)
        path = urlsplit(url).path.removeprefix("/v2/")
        if method == "POST":
            payload = kwargs["body"]
            root = next(iter(payload))
            if root == "attachments":
                return {"attachments": []}, {}
            return {root: {"url": BASE + path.split("?", 1)[0] + "/90"}}, {}
        if mode and mode[0] == "missing":
            result = provider_result(path)
            return {key: [] if isinstance(value, list) else {} for key, value in result.items()}, {}
        return provider_result(path), {}

    monkeypatch.setattr(
        "freeagent_ai.public_tools.download",
        lambda *_: {"file_name": "synthetic.pdf", "content_type": "application/pdf", "data": "JVBERi0="},
    )
    dispatcher = Dispatcher(accounts, "id", "secret", client_factory=lambda *a: HostedClient(*a, transport=transport))
    verifier = SimpleNamespace(principal=lambda token: denied if token == "denied" else read_write)
    with TestClient(create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN) as client:

        def rpc(name, args=None, token="synthetic"):
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": name, "params": args or {}},
            )
            assert response.status_code == 200
            return response.json()["result"]

        yield rpc, calls, mode


def cases():
    # Each skill's explicitly required entry points; referenced secondary operations
    # are also checked by discovery and static schema coverage below.
    return [(skill, name) for skill, names in SKILLS.items() for name in names]


@pytest.mark.parametrize("skill,name", cases())
def test_each_packaged_skill_has_a_real_provider_http_path(remote, skill, name):
    rpc, calls, _ = remote
    files = package_files(ROOT)
    contract = json.loads(files["docs/capabilities.json"])[skill]
    assert name in {op["name"] for op in contract["operations"]}
    assert contract["workflow_sha256"] == hashlib.sha256(files[f"skills/{skill}/SKILL.md"]).hexdigest()
    discovered = {tool["name"]: tool for tool in rpc("tools/list")["tools"]}
    for op in contract["operations"]:
        assert op["input_schema"] == discovered[op["name"]]["inputSchema"]
        assert op["endpoint"] and op["method"] in {"GET", "POST", "PUT", "DELETE"}
    operation = REGISTRY[name]
    result = rpc("tools/call", {"name": name, "arguments": sample_args(operation)})
    assert not result.get("isError"), result
    assert calls and calls[0][0] == operation.method
    expected = (
        operation.endpoint.replace("{user_id}", "1")
        .replace("{id}", "1")
        .replace("{period_ends_on}", "2026-01-01")
        .replace("{year}", "2026")
        .replace("{period}", "1")
    )
    expected_first = expected.removesuffix("/pdf")
    assert urlsplit(calls[0][1]).path == "/v2/" + expected_first
    assert result["structuredContent"]
    if operation.method == "POST":
        assert [method for method, _, _ in calls].count("POST") == 1
        assert any(method == "GET" for method, _, _ in calls), "Provider create must be read back"


@pytest.mark.parametrize("name", sorted({name for names in SKILLS.values() for name in names}))
def test_missing_scope_blocks_every_required_operation_before_provider(remote, name):
    rpc, calls, _ = remote
    result = rpc("tools/call", {"name": name, "arguments": sample_args(REGISTRY[name])}, token="denied")
    assert result["isError"]
    assert not calls


@pytest.mark.parametrize(
    "name",
    sorted(
        {
            name
            for names in SKILLS.values()
            for name in names
            if name.startswith("create_") or name.startswith("explain_")
        }
    ),
)
def test_refused_writes_never_reach_provider(remote, name):
    rpc, calls, _ = remote
    args = sample_args(REGISTRY[name])
    args["confirmed"] = False
    assert rpc("tools/call", {"name": name, "arguments": args})["isError"]
    assert not calls


def test_provider_error_missing_fields_and_uncertain_write_are_not_fabricated(remote):
    rpc, calls, mode = remote
    mode[:] = ["denied"]
    denied = rpc("tools/call", {"name": "list_invoices", "arguments": {}})
    assert denied["isError"] and "Read incomplete" in denied["content"][0]["text"]
    mode[:] = ["missing"]
    missing = rpc("tools/call", {"name": "get_invoice", "arguments": {"id": "1"}})
    assert missing["structuredContent"]["invoice"] == {}
    assert missing["structuredContent"]["collected_at"]
    mode[:] = ["readback"]
    calls.clear()
    result = rpc("tools/call", {"name": "create_contact", "arguments": sample_args(REGISTRY["create_contact"])})
    assert result["isError"]
    assert [method for method, _, _ in calls].count("POST") == 1
    assert "before any retry" in result["content"][0]["text"]


@pytest.mark.parametrize(
    "instruction",
    [
        "Run freeagent_ai.analysis.forecast with these inputs.",
        "from freeagent_ai.recurring import recurring_scenario",
        "Use preview.py to compute claims.",
        "Use an available calculator for mileage.",
        "Run a Python script locally.",
        "Run Python locally with no rounding.",
        "Use a local Python script, not a calculator.",
        "Download the PDF file but do not expose signed URLs.",
        "Never calculate tax, but use a local Python script.",
        "```python\nprint(1)\n```",
        "Call `find_contacts` before invoicing.",
        "Call `invented_handler` with this body.",
        "Invoke `download_document` for the user.",
        "Use the helper `custom_logic`.",
        "POST invoices with this body.",
        "GET expenses?view=all",
        "Use `freeagent_post`.",
        "Return a base64 PDF to the user.",
        "Save the file at /tmp/invoice.pdf.",
        "Calculate future cash balances from these invoices.",
        "Compute mileage rates and pooled thresholds.",
        "Do not assume Python; use an available calculator.",
        "If unavailable, use a calculator for the claim.",
    ],
)
def test_audited_client_runtime_and_executor_leaks_fail(instruction):
    with pytest.raises(ValueError):
        validate_workflow("skills/synthetic/SKILL.md", instruction)


@pytest.mark.parametrize(
    "instruction",
    [
        "No Python, scripts or client calculator is required. Never run a local accounting engine.\nCall `get_company`.",
        "Never use a local Python script. Call `get_company` instead.",
        "Do not use a calculator for accounting values.",
        "Do not download PDF files; no document output is supported.",
        "Never return a local file or base64 blob to the user.",
        "Do not compute mileage rates, pooled thresholds or monetary amounts.",
    ],
)
def test_prohibition_is_not_confused_with_a_runtime_requirement(instruction):
    validate_workflow("skills/synthetic/SKILL.md", instruction)


@pytest.mark.parametrize(
    "name,endpoint",
    [("calculate_recurring_scenario", "recurring_invoices"), ("forecast", ""), ("get_custom_snapshot", None)],
)
def test_remote_calculator_does_not_become_an_api_operation(monkeypatch, name, endpoint):
    monkeypatch.setitem(REGISTRY, name, replace(REGISTRY["get_company"], name=name, endpoint=endpoint))
    with pytest.raises(ValueError, match="Non-provider operation"):
        validate_operations()


def test_all_advertised_skills_and_required_operations_are_covered():
    files = package_files(ROOT)
    contract = coverage(files)
    assert set(contract) == set(SKILLS)
    bad = deepcopy(files)
    bad["skills/mileage/scripts/helper.py"] = b"# executable helper"
    with pytest.raises(ValueError, match="Executable client helper"):
        validate_contract(bad)
    bad = deepcopy(files)
    bad["skills/mileage/SKILL.md"] = (
        b"Only an inventory appendix.\n## Hosted transport\n`get_mileage_settings` `create_mileage_expense`"
    )
    with pytest.raises(ValueError, match="Missing required workflow operations"):
        validate_contract(bad)


def test_broken_docs_anchor_source_digests_and_retired_source_fail(tmp_path):
    files = package_files(ROOT)
    for mutation in ("missing", "anchor"):
        bad = deepcopy(files)
        bad["skills/mileage/SKILL.md"] += (
            b"\n[Required evidence](../../docs/missing.md)"
            if mutation == "missing"
            else b"\n[Required evidence](../../docs/api-notes.md#not-a-real-heading)"
        )
        with pytest.raises(ValueError, match="Missing packaged"):
            validate_contract(bad)
    bad = deepcopy(files)
    bad["docs/source-digests.json"] = b"{}"
    with pytest.raises(ValueError, match="digest coverage"):
        validate_contract(bad, root=ROOT)
    (tmp_path / "freeagent_ai").mkdir()
    (tmp_path / "freeagent_ai/analysis.py").write_text("def forecast(): pass")
    with pytest.raises(ValueError, match="Retired accounting engine"):
        validate_contract(files, root=tmp_path)


@pytest.mark.parametrize(
    "name",
    sorted(
        {
            op["name"]
            for contract in json.loads(package_files(ROOT)["docs/capabilities.json"]).values()
            for op in contract["operations"]
        }
    ),
)
def test_every_secondary_operation_named_by_a_workflow_reaches_provider(remote, name):
    # Separate principals/rate buckets per case, rather than exhausting a real minute's quota.
    rpc, calls, _ = remote
    discovered = {tool["name"] for tool in rpc("tools/list")["tools"]}
    assert name in discovered
    operation = REGISTRY[name]
    result = rpc("tools/call", {"name": name, "arguments": sample_args(operation)})
    assert not result.get("isError"), (name, result)
    assert calls and calls[0][0] == operation.method
    assert all(url.startswith(BASE) for _, url, _ in calls)
    if operation.method != "GET":
        assert [method for method, _, _ in calls].count(operation.method) == 1
        assert any(method == "GET" for method, _, _ in calls)


def test_fake_file_links_and_tampered_source_digests_fail():
    files = package_files(ROOT)
    bad = deepcopy(files)
    bad["skills/receipts/SKILL.md"] += b"\n[Download](file:///tmp/invoice.pdf)"
    with pytest.raises(ValueError, match="Unsupported packaged link"):
        validate_contract(bad)
    bad = deepcopy(files)
    sources = json.loads(bad["docs/source-digests.json"])
    sources["docs/analysis.md"] = "0" * 64
    bad["docs/source-digests.json"] = json.dumps(sources).encode()
    with pytest.raises(ValueError, match="digest mismatch"):
        validate_contract(bad, root=ROOT)


def test_artifact_and_approval_contracts_are_derived_from_discovered_schemas(remote):
    rpc, _, _ = remote
    contracts = json.loads(package_files(ROOT)["docs/capabilities.json"])
    tools = {tool["name"]: tool for tool in rpc("tools/list")["tools"]}
    receipts = contracts["receipts"]["input_artifacts"]
    assert {item["parameter"] for item in receipts} == {"receipt", "attachment"}
    for contract in contracts.values():
        assert contract["output_artifacts"] == ["provider JSON / assistant explanation"]
        for item in contract["input_artifacts"]:
            tool = tools[item["tool"]]
            assert item["parameter"] in tool["_meta"]["openai/fileParams"]
            assert item["input_schema"] == tool["inputSchema"]["properties"][item["parameter"]]
        for op in contract["operations"]:
            if op["method"] != "GET":
                assert op["approval_parameter"] == "confirmed"
                assert "confirmed" in op["input_schema"]["required"]


def test_canonical_sources_cannot_hide_in_the_generated_inventory():
    with pytest.raises(ValueError, match="reserved"):
        render_hosted("Call `get_company`.\n## Hosted transport\nRun Python locally.")
    with pytest.raises(ValueError, match="local generic executor"):
        render_hosted("Use freeagent_post with this body.")


def test_grouped_categories_are_read_through_mcp(remote):
    rpc, calls, mode = remote
    result = rpc("tools/call", {"name": "list_categories", "arguments": {}})
    assert not result.get("isError"), result
    categories = result["structuredContent"]["categories"]
    assert [item["nominal_code"] for item in categories] == ["1", "2", "3", "4"]
    assert all(item["url"].startswith(BASE + "categories/") for item in categories)
    assert all(method == "GET" for method, _, _ in calls)
    mode.append("missing")
    empty = rpc("tools/call", {"name": "list_categories", "arguments": {}})
    assert not empty.get("isError"), empty
    assert empty["structuredContent"] == {"categories": []}


@pytest.mark.parametrize("invalid", [None, {}, ["invalid"]])
def test_malformed_category_group_fails_instead_of_reporting_empty(remote, monkeypatch, invalid):
    original = provider_result

    def malformed(path):
        result = original(path)
        result["general_categories"] = invalid
        return result

    monkeypatch.setattr(__name__ + ".provider_result", malformed)
    rpc, _, _ = remote
    result = rpc("tools/call", {"name": "list_categories", "arguments": {}})
    assert result["isError"]
    assert "categories" not in result.get("structuredContent", {})


@pytest.mark.parametrize("root", ["invoice", "timeslip", "bill", "expense"])
def test_correction_readback_preserves_declared_output_without_read_metadata(remote, root):
    rpc, calls, _ = remote
    operation = REGISTRY["update_" + root]
    body = {root: {"description": "Approved synthetic correction"}}
    descriptor = next(item for item in rpc("tools/list")["tools"] if item["name"] == operation.name)
    assert "collected_at" not in descriptor["outputSchema"]["properties"]
    result = rpc("tools/call", {"name": operation.name, "arguments": {"id": "1", "body": body, "confirmed": True}})
    assert not result.get("isError", False)
    assert set(result["structuredContent"]) == {root}
    assert result["structuredContent"][root]["url"] == BASE + operation.endpoint.replace("{id}", "1")
    assert [(method, payload) for method, _, payload in calls] == [("PUT", body), ("GET", None)]
