"""Synthetic authenticated reads and explicit reviewed recurring scenarios."""

import time
import urllib.error
from copy import deepcopy
from datetime import date
from decimal import Decimal
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest

from freeagent_ai.analysis import IncompleteData, forecast
from freeagent_ai.hosted_accounts import Principal
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.public_package import package_files
from freeagent_ai.public_tools import REGISTRY, Dispatcher, audit
from freeagent_ai.recurring import billing_dates, recurring_scenario

BASE = "https://api.freeagent.com/v2/"
STAMP = "2026-01-01T00:00:00Z"


def profile(**overrides) -> dict[str, Any]:
    return dict(
        url=BASE + "recurring_invoices/1",
        contact=BASE + "contacts/7",
        reference="SYNTHETIC-1",
        frequency="Monthly",
        recurring_status="Active",
        next_recurs_on="2026-01-31",
        recurring_end_date="",
        currency="GBP",
        net_value="100",
        sales_tax_value="20",
        total_value="120",
        payment_terms_in_days=30,
        invoice_items=[dict(description="Synthetic service", quantity="1", price="100", private="hidden")],
        private="hidden",
        **overrides,
    )


@pytest.fixture
def recurring(accounts, hosted_context):
    accounts.replace(
        "recurring", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("recurring", frozenset({"freeagent:read"}), 101)
    rows = [profile(), {**profile(), "url": BASE + "recurring_invoices/2"}]
    calls = []
    failures = []

    def transport(method, url, deadline, **kwargs):
        assert method == "GET"
        calls.append(url)
        if failures:
            raise urllib.error.HTTPError(url, failures[0], "denied", Message(), None)
        parsed = urlsplit(url)
        if parsed.path.endswith("/1"):
            return {"recurring_invoice": deepcopy(rows[0])}, {}
        query = parse_qs(parsed.query)
        page = int(query.get("page", ["1"])[0])
        headers = {"Link": f'<{BASE}recurring_invoices?page=2>; rel="next"'} if page == 1 else {}
        return {"recurring_invoices": deepcopy(rows[:1] if page == 1 else rows[1:])}, headers

    dispatcher = Dispatcher(
        accounts, "dummy", "dummy", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )

    def invoke(name, **args):
        with hosted_context(principal):
            return dispatcher.invoke(name, args)

    return invoke, rows, calls, failures


def test_authenticated_fixed_reads_pagination_filters_and_safe_fields(recurring):
    invoke, _, calls, _ = recurring
    rows = invoke("list_recurring_invoices", view="active", contact="7")["recurring_invoices"]
    assert len(rows) == 2
    query = parse_qs(urlsplit(calls[0]).query)
    assert query["contact"] == [BASE + "contacts/7"]
    assert query["view"] == ["active"]
    assert "private" not in rows[0]
    assert rows[0]["invoice_items"] == [dict(description="Synthetic service", quantity="1", price="100")]
    assert rows[0]["frequency"] == "Monthly"
    assert rows[0]["next_recurs_on"] == "2026-01-31"
    assert invoke("get_recurring_invoice", id="1")["recurring_invoice"] == rows[0]
    assert len(calls) == 3
    assert REGISTRY["get_recurring_invoice"].method == "GET"
    assert not any("recurring" in op.name and op.method != "GET" for op in REGISTRY.values())
    assert "recurring_invoice" in str(audit())


@pytest.mark.parametrize("code", [403, 404, 500])
def test_failed_read_not_empty(recurring, code):
    invoke, _, _, failures = recurring
    failures.append(code)
    with pytest.raises(urllib.error.HTTPError):
        invoke("list_recurring_invoices", view="active")


def scenario(profiles=None, **overrides):
    selected = profiles or [profile()]
    defaults = dict(
        start=date(2026, 1, 1),
        end=date(2026, 3, 31),
        timestamp=STAMP,
        currency="GBP",
        profiles_by_view={"active": selected, "inactive": [], "draft": []},
        invoices=[],
        reads_complete=True,
        assumptions={
            row["url"]: dict(
                anchor="2026-01-31",
                end_inclusive=True,
                payment_delay_days=5,
                additional_dates=["2026-01-31", "2026-02-28", "2026-03-31"],
                generated={},
            )
            for row in selected
        },
    )
    return recurring_scenario(**{**defaults, **overrides})


def test_month_end_cash_dates_and_actual_forecast():
    result = scenario()
    assert result["status"] == "complete"
    assert [row["billing_date"] for row in result["events"]] == ["2026-01-31", "2026-02-28", "2026-03-31"]
    assert [row["expected_receipt_date"] for row in result["events"]] == ["2026-02-05", "2026-03-05", "2026-04-05"]
    out = forecast(
        start=date(2026, 1, 1),
        timestamp=STAMP,
        currency="GBP",
        accounts=[dict(url=BASE + "bank_accounts/1", currency="GBP", current_balance="0")],
        invoices=[],
        bills=[],
        commitments=result["commitments"],
        missing_inputs=result["missing_inputs"],
    )
    assert out["status"] == "complete"
    assert sum(row["receipts"] for row in out["weeks"]) == Decimal("240")
    assert out["outside_horizon"] == [BASE + "recurring_invoices/1#scenario-2026-03-31"]


@pytest.mark.parametrize(
    "frequency,expected",
    [
        ("Weekly", "2026-02-07"),
        ("Two Weekly", "2026-02-14"),
        ("Four Weekly", "2026-02-28"),
        ("Monthly", "2026-02-28"),
        ("Two Monthly", "2026-03-31"),
        ("Quarterly", "2026-04-30"),
        ("Biannually", "2026-07-31"),
        ("Annually", "2027-01-31"),
        ("2-Yearly", "2028-01-31"),
    ],
)
def test_all_documented_cadences(frequency, expected):
    row = profile()
    row["frequency"] = frequency
    dates = billing_dates(row, anchor=date(2026, 1, 31), end=date.fromisoformat(expected))
    assert dates == [date(2026, 1, 31), date.fromisoformat(expected)]


def test_leap_anchor_does_not_drift_and_finite_end_inclusive():
    row = profile()
    row.update(frequency="Annually", next_recurs_on="2025-02-28", recurring_end_date="2028-02-29")
    assert billing_dates(row, anchor=date(2024, 2, 29), end=date(2030, 1, 1)) == [
        date(2025, 2, 28),
        date(2026, 2, 28),
        date(2027, 2, 28),
        date(2028, 2, 29),
    ]
    row.update(frequency="Monthly", next_recurs_on="2026-02-28", recurring_end_date="2026-04-29")
    assert billing_dates(row, anchor=date(2026, 1, 31), end=date(2026, 5, 1)) == [date(2026, 2, 28), date(2026, 3, 31)]


def test_inactive_and_draft_visible_but_no_receipts():
    row = profile()
    inactive = {**row, "url": BASE + "recurring_invoices/2"}
    draft = {**row, "url": BASE + "recurring_invoices/3", "recurring_status": "Draft"}
    result = scenario(profiles_by_view={"active": [], "inactive": [inactive], "draft": [draft]})
    assert result["status"] == "complete"
    assert result["groups"]["inactive"] == [inactive["url"]]
    assert result["groups"]["draft"] == [draft["url"]]
    assert result["commitments"] == []


@pytest.mark.parametrize("status", ["Open", "Paid", "Draft"])
def test_generated_invoice_not_counted_again(status):
    source = profile()["url"]
    result = scenario(
        invoices=[dict(url=BASE + "invoices/7", currency="GBP", dated_on="2026-01-31", status=status)],
        assumptions={
            source: dict(
                anchor="2026-01-31",
                end_inclusive=True,
                payment_delay_days=5,
                additional_dates=["2026-02-28", "2026-03-31"],
                generated={"2026-01-31": BASE + "invoices/7"},
            )
        },
    )
    assert result["status"] == "complete"
    assert len(result["commitments"]) == 2
    assert result["events"][0]["status"] == "already_generated"
    assert result["events"][0]["invoice"] == BASE + "invoices/7"


@pytest.mark.parametrize(
    "review",
    [
        {},
        dict(anchor="2026-01-31"),
        dict(anchor="2026-01-30", end_inclusive=True),
        dict(anchor="2026-01-31", end_inclusive=True, additional_dates=[]),
        dict(anchor="2026-01-31", end_inclusive=True, additional_dates=["2026-01-31"]),
        dict(
            anchor="2026-01-31",
            end_inclusive=True,
            payment_delay_days=5,
            generated={"2026-01-31": BASE + "invoices/404"},
        ),
        dict(
            anchor="2026-01-31",
            end_inclusive=True,
            payment_delay_days=5,
            generated={"2026-01-31": BASE + "invoices/7"},
            additional_dates=["2026-01-31"],
        ),
    ],
)
def test_missing_or_conflicting_assumptions_incomplete(review):
    result = scenario(assumptions={profile()["url"]: review})
    assert result["status"] == "incomplete"
    assert result["missing_inputs"]
    assert result["commitments"] == []


def test_failed_collections_suppress_all_commitments():
    result = scenario(reads_complete=False)
    assert result["status"] == "incomplete"
    assert result["commitments"] == []


def test_currency_scope_unsupported_stale_and_missing_fields():
    for changes in [dict(currency="EUR"), dict(frequency="Daily"), dict(next_recurs_on="2025-12-31")]:
        row = profile()
        row.update(changes)
        assert scenario([row])["status"] == "incomplete"
    row = profile()
    del row["total_value"]
    assert scenario([row])["commitments"] == []
    row = profile()
    row["currency"] = "EUR"
    result = scenario([row], currency="EUR")
    assert result["status"] == "complete"
    assert {x["currency"] for x in result["commitments"]} == {"EUR"}


def test_duplicate_groups_and_missing_views_are_not_complete():
    with pytest.raises(ValueError, match="unique"):
        scenario(profiles_by_view={"active": [profile()], "inactive": [profile()], "draft": []})
    with pytest.raises(IncompleteData):
        scenario(profiles_by_view={"active": [profile()]})


def test_scenario_from_actual_hosted_dispatcher(recurring):
    invoke, rows, _, _ = recurring
    rows.pop()
    active = invoke("list_recurring_invoices", view="active")["recurring_invoices"]
    result = scenario(active)
    assert result["status"] == "complete"
    assert result["events"][0]["amount"] == Decimal("120")


def test_canonical_workflow_and_doc_are_packaged_with_digests():
    root = Path(__file__).resolve().parents[1]
    files = package_files(root)
    assert b"docs/recurring-revenue.md" in files["docs/source-digests.json"]
    assert b"list_recurring_invoices" in files["skills/recurring-revenue/SKILL.md"]
    assert b"unknown or conflicting evidence remains incomplete" in files["docs/recurring-revenue.md"]


@pytest.mark.parametrize(
    "invoice",
    [
        dict(url=BASE + "invoices/7", currency="EUR", dated_on="2026-01-31"),
        dict(url=BASE + "invoices/7", currency="GBP", dated_on="2026-02-01"),
    ],
)
def test_edited_or_wrong_currency_generated_invoice_needs_reconciliation(invoice):
    result = scenario(
        invoices=[invoice],
        assumptions={
            profile()["url"]: dict(
                anchor="2026-01-31", end_inclusive=True, generated={"2026-01-31": BASE + "invoices/7"}
            )
        },
    )
    assert result["status"] == "incomplete"
    assert result["commitments"] == []
    assert "mismatched" in result["missing_inputs"][0]


def test_complete_empty_views_are_distinct_from_failed_reads():
    result = scenario(profiles_by_view={"active": [], "inactive": [], "draft": []})
    assert result["status"] == "complete"
    assert result["events"] == []
    incomplete = scenario(profiles_by_view={"active": [], "inactive": [], "draft": []}, reads_complete=False)
    assert incomplete["status"] == "incomplete"
    assert incomplete["missing_inputs"]
