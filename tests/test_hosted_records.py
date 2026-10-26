"""Provider record evidence collected through the authenticated hosted dispatcher."""

import importlib.util
import time
import urllib.error
from copy import deepcopy
from email.message import Message
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import settings
from mcp.types import TextContent
from starlette.testclient import TestClient

from freeagent_ai.hosted_accounts import Principal
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.public_tools import REGISTRY, Dispatcher, audit

BASE = "https://api.freeagent.com/v2/"
STAMP = "2026-01-01T00:00:00Z"


def sources():
    return {
        "bank_accounts": [
            dict(
                url=BASE + "bank_accounts/1",
                currency="GBP",
                current_balance="1000",
                latest_activity_date="2025-12-31",
                is_personal=False,
            )
        ],
        "projects": [
            dict(
                url=BASE + "projects/1",
                contact=BASE + "contacts/1",
                currency="GBP",
                budget="5",
                budget_units="Days",
                hours_per_day="8",
            )
        ],
        "tasks": [dict(url=BASE + f"tasks/{i}", project=BASE + "projects/1", is_billable=bool(i == 1)) for i in (1, 2)],
        "timeslips": [
            dict(
                url=BASE + f"timeslips/{i}",
                project=BASE + "projects/1",
                task=BASE + f"tasks/{2 if i == 3 else 1}",
                user=BASE + "users/1",
                dated_on="2026-01-01",
                hours="2",
                **({"billed_on_invoice": BASE + "invoices/2"} if i == 1 else {}),
            )
            for i in (1, 2, 3)
        ],
        "invoices": [
            dict(
                url=BASE + "invoices/1",
                project=BASE + "projects/1",
                dated_on="2026-01-01",
                due_on="2026-01-02",
                currency="GBP",
                status="Open",
                net_value="500",
                due_value="400",
            ),
            dict(
                url=BASE + "invoices/2",
                project=BASE + "projects/1",
                dated_on="2026-01-01",
                due_on="2026-01-02",
                currency="GBP",
                status="Draft",
                net_value="200",
                due_value="200",
            ),
        ],
        "credit_notes": [
            dict(
                url=BASE + "credit_notes/1",
                project=BASE + "projects/1",
                dated_on="2026-01-01",
                due_on="2026-01-03",
                currency="GBP",
                status="Open",
                net_value="-100",
                total_value="-120",
                due_value="-60",
                refunded_value="0",
                credit_note_items=[
                    dict(
                        url=BASE + "credit_note_items/1",
                        project=BASE + "projects/1",
                        invoice_item=BASE + "invoice_items/1",
                        quantity="-1",
                        price="100",
                    )
                ],
            )
        ],
        "credit_note_reconciliations": [
            dict(
                url=BASE + "credit_note_reconciliations/1",
                credit_note=BASE + "credit_notes/1",
                invoice=BASE + "invoices/1",
                dated_on="2026-01-01",
                currency="GBP",
                gross_value="60",
                exchange_rate="1",
            )
        ],
        "expenses": [
            dict(
                url=BASE + "expenses/1",
                project=BASE + "projects/1",
                dated_on="2026-01-01",
                currency="GBP",
                gross_value="-24",
                sales_tax_value="-4",
                native_gross_value="-24",
                rebilled_on_invoice=BASE + "invoices/2",
            )
        ],
        "bills": [
            dict(
                url=BASE + "bills/1",
                project=BASE + "projects/1",
                dated_on="2026-01-01",
                due_on="2026-01-02",
                currency="GBP",
                status="Open",
                net_value="50",
                total_value="60",
                due_value="60",
                bill_items=[
                    dict(
                        url=BASE + "bill_items/1",
                        project=BASE + "projects/1",
                        total_value_ex_tax="50",
                        sales_tax_value="10",
                    )
                ],
            )
        ],
    }


@pytest.fixture
def collect(accounts, hosted_context):
    accounts.replace(
        "analysis", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("analysis", frozenset({"freeagent:read"}), 101)
    data = sources()
    data["credit_notes"].append({**data["credit_notes"][0], "url": BASE + "credit_notes/2", "status": "Draft"})
    calls = []

    def transport(method, url, deadline, **kwargs):
        assert method == "GET"
        parsed = urlsplit(url)
        path = parsed.path.removeprefix("/v2/")
        endpoint, _, identifier = path.partition("/")
        calls.append(url)
        rows = deepcopy(data[endpoint])
        if identifier:
            root = {"credit_notes": "credit_note", "credit_note_reconciliations": "credit_note_reconciliation"}[
                endpoint
            ]
            return {
                "credit_note_reconciliations" if endpoint == "credit_note_reconciliations" else root: rows[
                    int(identifier) - 1
                ]
            }, {}
        # Actual HostedClient pagination, including the new credit-note collections.
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        headers = {"Link": f'<{BASE}{endpoint}?page=2&per_page=1>; rel="next"'} if page == 1 and len(rows) > 1 else {}
        return {endpoint: rows[:1] if page == 1 else rows[1:]}, headers

    dispatcher = Dispatcher(
        accounts, "dummy", "dummy", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )

    def read(endpoint, **arguments):
        with hosted_context(principal):
            return dispatcher.invoke("list_" + endpoint, arguments)[endpoint]

    return read, data, dispatcher, principal, calls


def test_hosted_records_preserve_provider_values_and_relationships(collect):
    read, _, _, _, calls = collect
    assert read("projects")[0] == dict(
        url=BASE + "projects/1",
        contact=BASE + "contacts/1",
        currency="GBP",
        budget="5",
        budget_units="Days",
        hours_per_day="8",
    )
    tasks = read("tasks")
    assert [task["is_billable"] for task in tasks] == [True, False]
    slips = read("timeslips")
    assert slips[0]["billed_on_invoice"] == BASE + "invoices/2"
    assert "billed_on_invoice" not in slips[1]
    assert [row["status"] for row in read("invoices")] == ["Open", "Draft"]
    assert [row["status"] for row in read("credit_notes")] == ["Open", "Draft"]
    assert read("expenses")[0]["gross_value"] == "-24"
    assert read("bills")[0]["bill_items"][0]["total_value_ex_tax"] == "50"
    assert any("credit_notes?page=2" in call for call in calls)


def test_credit_and_reconciliation_evidence_are_not_reinterpreted(collect):
    read, _, _, _, _ = collect
    credit = read("credit_notes")[0]
    assert credit["net_value"] == "-100"
    assert credit["total_value"] == "-120"
    assert credit["due_value"] == "-60"
    assert credit["refunded_value"] == "0"
    reconciliation = read("credit_note_reconciliations")[0]
    assert reconciliation["gross_value"] == "60"
    assert reconciliation["credit_note"] == credit["url"]
    assert reconciliation["invoice"] == BASE + "invoices/1"


@pytest.mark.parametrize(
    "endpoint,field",
    [
        ("tasks", "is_billable"),
        ("timeslips", "hours"),
        ("credit_notes", "net_value"),
        ("projects", "hours_per_day"),
        ("bank_accounts", "current_balance"),
    ],
)
def test_missing_provider_values_remain_absent(collect, endpoint, field):
    read, data, _, _, _ = collect
    data[endpoint][0].pop(field)
    assert field not in read(endpoint)[0]


def test_running_timer_evidence_is_retained_without_deriving_hours(collect):
    read, data, _, _, _ = collect
    data["timeslips"][0]["timer"] = dict(running=True, start_from=STAMP, secret="omit")
    slip = read("timeslips")[0]
    assert slip["timer"] == dict(running=True, start_from=STAMP)
    assert slip["hours"] == "2"


def test_provider_currency_is_preserved_without_conversion(collect):
    read, data, _, _, _ = collect
    data["credit_notes"][0]["currency"] = "USD"
    assert read("credit_notes")[0]["currency"] == "USD"
    assert read("invoices")[0]["currency"] == "GBP"


def test_custom_analysis_runtime_and_tools_are_absent():
    assert importlib.util.find_spec("freeagent_ai.analysis") is None
    assert not {"calculate_cash_flow", "calculate_profitability", "forecast", "profitability"} & REGISTRY.keys()


def test_fixed_credit_reads_and_audit(collect, hosted_context):
    _, data, dispatcher, principal, _ = collect
    with hosted_context(principal):
        assert dispatcher.invoke("get_credit_note", {"id": "1"})["credit_note"]["due_value"] == "-60"
        assert (
            dispatcher.invoke("get_credit_note_reconciliation", {"id": "1"})["credit_note_reconciliation"]
            == data["credit_note_reconciliations"][0]
        )
    for name in (
        "list_credit_notes",
        "get_credit_note",
        "list_credit_note_reconciliations",
        "get_credit_note_reconciliation",
    ):
        assert REGISTRY[name].descriptor.annotations.read_only_hint
        assert next(row for row in audit() if row["name"] == name)["method"] == "GET"


@pytest.mark.parametrize("failure", ["permission", "timeout", "bad_projection"])
def test_failed_hosted_reads_explicitly_report_incomplete(accounts, hosted_context, failure):
    accounts.replace(
        "analysis", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )

    def transport(method, url, deadline, **kwargs):
        if failure == "permission":
            raise urllib.error.HTTPError(url, 403, "denied", Message(), BytesIO(b"{}"))
        if failure == "timeout":
            raise TimeoutError()
        return {"credit_notes": [{"timer": {"running": "bad"}}]}, {}

    # A wrong provider scalar also fails the output schema after projection.
    if failure == "bad_projection":

        def transport(method, url, deadline, **kwargs):
            return {"credit_notes": [{"net_value": {"unexpected": "object"}}]}, {}

    dispatcher = Dispatcher(
        accounts, "dummy", "dummy", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    with hosted_context(Principal("analysis", frozenset({"freeagent:read"}), 101)):
        result = dispatcher.call_tool("list_credit_notes", {})
    assert result.is_error
    assert isinstance(result.content[0], TextContent)
    assert "Read incomplete" in result.content[0].text


def test_credit_note_filters_expand_fixed_resource_ids(collect):
    read, _, _, _, calls = collect
    assert read("credit_notes", contact="1", project="1")
    query = parse_qs(urlsplit(calls[0]).query)
    assert query["contact"] == [BASE + "contacts/1"]
    assert query["project"] == [BASE + "projects/1"]


def test_hosted_expense_preserves_native_and_manual_tax_evidence(collect):
    read, data, _, _, _ = collect
    data["expenses"][0].update(
        currency="USD",
        gross_value="-30",
        sales_tax_value="-5",
        native_gross_value="-24",
        native_sales_tax_value="-4",
        manual_sales_tax_amount="-3.50",
    )
    expense = read("expenses")[0]
    assert expense["currency"] == "USD"
    assert expense["gross_value"] == "-30"
    assert expense["sales_tax_value"] == "-5"
    assert expense["native_gross_value"] == "-24"
    assert expense["native_sales_tax_value"] == "-4"
    assert expense["manual_sales_tax_amount"] == "-3.50"


def test_retained_provider_reads_are_discovered_and_invoked_over_http(collect, accounts):
    _, data, dispatcher, principal, calls = collect
    verifier = SimpleNamespace(principal=lambda _: principal)
    with TestClient(create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN) as client:
        headers = {"Authorization": "Bearer synthetic", "Accept": "application/json, text/event-stream"}
        tools = client.post(
            "/mcp",
            headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        ).json()["result"]["tools"]
        names = {tool["name"] for tool in tools}
        assert "list_credit_notes" in names
        assert not {"forecast", "profitability", "calculate_cash_flow", "calculate_profitability"} & names
        result = client.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "list_credit_notes", "arguments": {}},
            },
        )
        assert result.status_code == 200
        assert result.json()["result"]["structuredContent"]["credit_notes"] == data["credit_notes"]
        assert any("credit_notes?page=2" in call for call in calls)
