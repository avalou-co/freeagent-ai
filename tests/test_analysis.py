"""Synthetic reconciliations for read-only forecast and profitability arithmetic."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from freeagent_ai.analysis import forecast, number, profitability

START = date(2026, 1, 1)


def cash(**changes):
    inputs: dict[str, Any] = dict(
        start=START,
        timestamp="2026-01-01T00:00:00Z",
        currency="GBP",
        accounts=[dict(url="bank/1", currency="GBP", current_balance="100.10")],
        invoices=[],
        bills=[],
        commitments=[],
        missing_inputs=[],
    )
    return forecast(**(inputs | changes))


def invoice(**changes):
    return (
        dict(
            url="invoice/1", currency="GBP", status="Open", due_value="50.20", total_value="100.00", due_on="2025-12-01"
        )
        | changes
    )


def test_partial_overdue_paid_and_scenarios():
    inputs: dict[str, Any] = dict(
        invoices=[invoice(), invoice(url="invoice/paid", status="Paid", due_value="0")],
        bills=[invoice(url="bill/1", due_value="170.40", due_on="2026-01-08")],
    )
    on_time = cash(**inputs)
    assert on_time["weeks"][0]["closing"] == Decimal("150.30")
    assert on_time["weeks"][1]["closing"] == Decimal("-20.10")
    assert on_time["first_shortfall"] == "2026-01-08"
    assert on_time["overdue"] == ["invoice/1"]
    assert on_time["excluded"] == ["invoice/paid"]
    delayed = cash(**inputs, receipt_delay_days=14)
    assert delayed["weeks"][0]["receipts"] == 0
    assert delayed["weeks"][1]["closing"] == Decimal("-70.30")
    assert delayed["weeks"][2]["closing"] == Decimal("-20.10")
    assert delayed["weeks"][2]["sources"] == ["invoice/1"]


def test_empty_custom_and_horizon():
    assert len(cash()["weeks"]) == 13
    assert cash()["weeks"][-1]["closing"] == Decimal("100.10")
    commitment = dict(url="commit/payroll/1", currency="GBP", amount="-200", date="2026-01-01", additional=True)
    assert cash(commitments=[commitment])["first_shortfall"] == "2026-01-01"
    assert cash(invoices=[invoice()], receipt_delay_days=91)["outside_horizon"] == ["invoice/1"]


def test_currency_duplicates_and_unreviewed_commitments():
    with pytest.raises(ValueError, match="currencies"):
        cash(invoices=[invoice(currency="USD")])
    with pytest.raises(ValueError, match="unique"):
        cash(invoices=[invoice(), invoice()])
    with pytest.raises(ValueError, match="additional"):
        cash(commitments=[dict(url="commit/1", currency="GBP", additional=False)])
    with pytest.raises(ValueError, match="Refunds"):
        cash(invoices=[invoice(due_value="-2")])


@pytest.mark.parametrize("value", [1.1, "NaN", "Infinity", "bad", None])
def test_invalid_numbers(value):
    with pytest.raises(ValueError):
        number(value)


def project_report(**changes):
    project = dict(url="project/1", contact="contact/1", currency="GBP", budget="20", budget_units="Hours")
    task = dict(url="task/1", project="project/1", is_billable=True)
    slip = dict(
        url="time/1",
        project="project/1",
        task="task/1",
        user="user/1",
        dated_on="2026-01-01",
        hours="10",
        billed_on_invoice="invoice/1",
    )
    inv = dict(
        url="invoice/1",
        project="project/1",
        currency="GBP",
        dated_on="2026-01-02",
        status="Open",
        net_value="1000",
        paid_value="300",
    )
    inputs: dict[str, Any] = dict(
        start=START,
        end=date(2026, 1, 31),
        timestamp="2026-02-01T00:00:00Z",
        projects=[project],
        tasks=[task],
        timeslips=[slip],
        invoices=[inv],
        costs=[],
        cost_rates={"user/1": "25"},
        costs_complete=True,
        credit_notes=[],
    )
    return profitability(**(inputs | changes))


def test_partial_billing_nonbillable_and_fixed_fee():
    slips = [
        dict(
            url="time/1",
            project="project/1",
            task="task/1",
            user="user/1",
            dated_on="2026-01-01",
            hours="10",
            billed_on_invoice="invoice/1",
        ),
        dict(url="time/2", project="project/1", task="task/1", user="user/1", dated_on="2026-01-02", hours="2"),
        dict(url="time/3", project="project/1", task="task/2", user="user/1", dated_on="2026-01-03", hours="4"),
    ]
    tasks = [
        dict(url="task/1", project="project/1", is_billable=True),
        dict(url="task/2", project="project/1", is_billable=False),
    ]
    result = project_report(timeslips=slips, tasks=tasks)["projects"][0]
    assert (result["hours"], result["billable_hours"], result["unbilled_hours"]) == (16, 12, 2)
    assert result["invoiced_net_revenue"] == 1000  # not settlement or time value
    assert result["realised_hourly_revenue"] == Decimal("62.5")
    assert result["time_cost"] == 400
    assert result["margin"] == 600
    assert result["period_budget_fraction"] == Decimal("0.8")
    assert result["unbilled_sources"] == ["time/2"]
    # Fixed fee with no time must not divide by zero or invent hourly work.
    assert project_report(timeslips=[])["projects"][0]["realised_hourly_revenue"] is None


def test_missing_costs_unattributed_and_budget_units():
    expense = dict(url="expense/1", dated_on="2026-01-01", currency="GBP", amount="50")
    report = project_report(cost_rates={}, costs=[expense], costs_complete=False)
    assert report["projects"][0]["margin"] is None
    assert report["projects"][0]["time_cost"] is None
    assert report["unattributed_costs"] == [expense]
    for units, budget, extra, expected in [
        ("Days", "5", {"hours_per_day": "8"}, Decimal("1.25")),
        ("Monetary", "2000", {}, Decimal("1000")),
    ]:
        project = dict(url="project/1", contact="contact/1", currency="GBP", budget=budget, budget_units=units) | extra
        assert project_report(projects=[project])["projects"][0]["period_budget_usage"] == expected


def test_period_boundaries_and_draft_time_link():
    slip = dict(
        url="time/1",
        project="project/1",
        task="task/1",
        user="user/1",
        dated_on="2026-01-31",
        hours="1",
        billed_on_invoice="invoice/draft",
    )
    result = project_report(timeslips=[slip])["projects"][0]
    assert result["unbilled_hours"] == 0
    assert result["hours"] == 1
    slip["dated_on"] = "2026-02-01"
    assert project_report(timeslips=[slip])["projects"][0]["hours"] == 0


def test_optional_budget_and_known_costs():
    project = dict(url="project/1", contact="contact/1", currency="GBP")
    result = project_report(projects=[project])["projects"][0]
    assert result["budget"] is None
    assert result["period_budget_usage"] is None
    assert result["period_budget_fraction"] is None
    costs = [
        dict(url="cost/1", project="project/1", dated_on="2026-01-01", currency="GBP", amount="100"),
        dict(url="cost/refund", project="project/1", dated_on="2026-01-01", currency="GBP", amount="-20"),
    ]
    assert project_report(costs=costs)["projects"][0]["margin"] == 670


def test_current_balance_requires_matching_snapshot_date():
    with pytest.raises(ValueError, match="snapshot date"):
        cash(start=date(2026, 1, 2))


def test_credit_notes_reduce_net_revenue_and_margin():
    credit = dict(
        url="credit_notes/1",
        project="project/1",
        currency="GBP",
        dated_on="2026-01-31",
        status="Open",
        net_value="-100",
    )
    result = project_report(credit_notes=[credit])["projects"][0]
    assert result["invoiced_net_revenue"] == 900
    assert result["margin"] == 650
    assert "credit_notes/1" in result["sources"]


def test_transfer_within_selected_accounts_does_not_create_forecast_events():
    accounts = [
        dict(url="bank/1", currency="GBP", current_balance="40.10"),
        dict(url="bank/2", currency="GBP", current_balance="60.00"),
    ]
    result = cash(accounts=accounts)
    assert result["weeks"][0]["closing"] == Decimal("100.10")
    assert result["weeks"][0]["receipts"] == result["weeks"][0]["payments"] == 0
