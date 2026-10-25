"""Synthetic skill snapshots collected through the authenticated hosted dispatcher."""

import time
import urllib.error
from copy import deepcopy
from datetime import date
from decimal import Decimal
from email.message import Message
from io import BytesIO
from urllib.parse import parse_qs, urlsplit

import pytest
from mcp.types import TextContent

from freeagent_ai.analysis import IncompleteData, forecast, profitability
from freeagent_ai.hosted_accounts import Principal
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


def calculate(read):
    projects, tasks, slips, invoices, credits, expenses, bills = [
        read(name) for name in ("projects", "tasks", "timeslips", "invoices", "credit_notes", "expenses", "bills")
    ]
    # Reviewed GBP allocations: never count bill header and lines together.
    costs = [
        dict(
            url=e["url"],
            project=e["project"],
            dated_on=e["dated_on"],
            currency=e["currency"],
            amount=str(-(Decimal(e["gross_value"]) - Decimal(e["sales_tax_value"]))),
        )
        for e in expenses
    ]
    costs += [
        dict(url=b["url"], project=b["project"], dated_on=b["dated_on"], currency=b["currency"], amount=b["net_value"])
        for b in bills
    ]
    return profitability(
        start=date(2026, 1, 1),
        end=date(2026, 1, 31),
        timestamp=STAMP,
        projects=projects,
        tasks=tasks,
        timeslips=slips,
        invoices=invoices,
        credit_notes=credits,
        costs=costs,
        cost_rates={BASE + "users/1": "10"},
        costs_complete=True,
    )


def test_hosted_profitability_reconciles_draft_time_credit_and_costs(collect):
    read, _, _, _, calls = collect
    result = calculate(read)
    row = result["projects"][0]
    assert result["status"] == "complete"
    assert (row["hours"], row["billable_hours"], row["unbilled_hours"]) == (6, 4, 2)
    assert row["unbilled_sources"] == [BASE + "timeslips/2"]
    assert (row["invoiced_net_revenue"], row["direct_cost"], row["margin"]) == (400, 70, 270)
    assert row["period_budget_usage"] == Decimal("0.75")
    assert any("credit_notes?page=2" in call for call in calls)


def test_hosted_forecast_reviewed_refund_is_not_allocation(collect):
    read, _, _, _, _ = collect
    credit = read("credit_notes")[0]
    reconciliation = read("credit_note_reconciliations")[0]
    assert reconciliation["gross_value"] == "60"
    # User confirms remaining refund, date, account assignment and no overlap.
    commitment = dict(
        url=credit["url"],
        currency=credit["currency"],
        date=credit["due_on"],
        amount=credit["due_value"],
        additional=True,
    )
    result = forecast(
        start=date(2026, 1, 1),
        timestamp=STAMP,
        currency="GBP",
        accounts=read("bank_accounts"),
        invoices=read("invoices"),
        bills=read("bills"),
        commitments=[commitment],
        missing_inputs=[],
    )
    assert result["status"] == "complete"
    assert (result["weeks"][0]["receipts"], result["weeks"][0]["payments"], result["weeks"][0]["closing"]) == (
        400,
        120,
        1280,
    )
    assert result["excluded"] == [BASE + "invoices/2"]


@pytest.mark.parametrize(
    "endpoint,field",
    [("tasks", "is_billable"), ("timeslips", "hours"), ("credit_notes", "net_value"), ("projects", "hours_per_day")],
)
def test_missing_provider_fields_fail_explicitly(collect, endpoint, field):
    read, data, _, _, _ = collect
    data[endpoint][0].pop(field)
    with pytest.raises(IncompleteData, match="Incomplete"):
        calculate(read)


def test_running_timer_is_retained_and_prevents_calculation(collect):
    read, data, _, _, _ = collect
    data["timeslips"][0]["timer"] = dict(running=True, start_from=STAMP, secret="omit")
    assert read("timeslips")[0]["timer"] == dict(running=True, start_from=STAMP)
    with pytest.raises(ValueError, match="running timers"):
        calculate(read)


def test_mixed_currency_does_not_produce_margin(collect):
    read, data, _, _, _ = collect
    data["credit_notes"][0]["currency"] = "USD"
    with pytest.raises(ValueError, match="currency"):
        calculate(read)


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


def test_provisional_inputs_remain_explicit(collect):
    read, _, _, _, _ = collect
    result = forecast(
        start=date(2026, 1, 1),
        timestamp=STAMP,
        currency="GBP",
        accounts=read("bank_accounts"),
        invoices=[],
        bills=[],
        commitments=[],
        missing_inputs=["Payroll not confirmed"],
    )
    assert result["status"] == "incomplete"
    assert result["missing_inputs"] == ["Payroll not confirmed"]


def test_missing_cash_balance_is_not_zero(collect):
    read, data, _, _, _ = collect
    data["bank_accounts"][0].pop("current_balance")
    with pytest.raises(IncompleteData, match="current_balance"):
        forecast(
            start=date(2026, 1, 1),
            timestamp=STAMP,
            currency="GBP",
            accounts=read("bank_accounts"),
            invoices=[],
            bills=[],
            commitments=[],
            missing_inputs=[],
        )
