"""Tax reads use the real authenticated dispatcher and hosted pagination transport."""

import time
import urllib.error
from copy import deepcopy
from datetime import date
from decimal import Decimal
from email.message import Message
from typing import Any
from urllib.parse import parse_qs, urlsplit

import jsonschema
import pytest

from freeagent_ai.analysis import forecast
from freeagent_ai.hosted_accounts import Principal
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.public_tools import REGISTRY, TAX_RETURNS, Dispatcher, audit

BASE = "https://api.freeagent.com/v2/"


@pytest.fixture
def tax(accounts, hosted_context):
    accounts.replace(
        "tax", BASE + "company/1", "production", {"access_token": "dummy", "expires_at": time.time() + 3600}, 0
    )
    principal = Principal("tax", frozenset({"freeagent:read"}), 101)
    calls = []
    rows = [
        dict(
            url=BASE + "vat_returns/2026-03-31",
            period_starts_on="2026-01-01",
            period_ends_on="2026-03-31",
            filing_due_on="2026-05-07",
            filing_status="pending",
            payments=[
                dict(label="Payment Due", due_on="2026-05-07", amount_due="120", status="unpaid", private="hidden")
            ],
            private="hidden",
        )
    ]
    failure = []

    def transport(method, url, deadline, **kwargs):
        assert method == "GET"
        calls.append(url)
        if failure:
            raise urllib.error.HTTPError(url, failure[0], "denied", Message(), None)
        parsed = urlsplit(url)
        path = parsed.path.removeprefix("/v2/")
        endpoint = next(e for e in TAX_RETURNS if path.startswith(e.replace("{user_id}", "7")))
        root = TAX_RETURNS[endpoint]
        endpoint_path = endpoint.replace("{user_id}", "7")
        if path != endpoint_path:
            return {root: deepcopy(rows[0])}, {}
        page = int(parse_qs(parsed.query).get("page", ["1"])[0])
        headers = {"Link": f'<{BASE}{endpoint_path}?page=2>; rel="next"'} if len(rows) > 1 and page == 1 else {}
        return {root + "s": deepcopy(rows[:1] if page == 1 else rows[1:])}, headers

    dispatcher = Dispatcher(
        accounts, "dummy", "dummy", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )

    def invoke(name, **args):
        with hosted_context(principal):
            return dispatcher.invoke(name, args)

    return invoke, rows, calls, failure


@pytest.mark.parametrize("endpoint,root", TAX_RETURNS.items())
def test_fixed_tax_list_detail_and_payment_projection(tax, endpoint, root):
    invoke, rows, calls, _ = tax
    args = {"user_id": "7"} if "users/" in endpoint else {}
    rows.append({**rows[0], "period_ends_on": "2026-06-30", "filing_status": "rejected"})
    records = invoke("list_" + root + "s", **args)[root + "s"]
    assert len(records) == 2
    assert records[1]["filing_status"] == "rejected"
    assert "private" not in records[0]
    if root != "corporation_tax_return":
        assert records[0]["payments"] == [
            dict(label="Payment Due", due_on="2026-05-07", amount_due="120", status="unpaid")
        ]
    detail = invoke("get_" + root, period_ends_on="2026-03-31", **args)[root]
    assert detail == records[0]
    assert calls[-1].endswith(endpoint.replace("{user_id}", "7") + "/2026-03-31")
    assert len(calls) == 3


def test_ct_distinct_filing_payment_dates_and_zero_missing_status(tax):
    invoke, rows, _, _ = tax
    rows[0].update(amount_due="0", payment_due_on="2026-01-01", filing_due_on="2026-03-31")
    result = invoke("get_corporation_tax_return", period_ends_on="2026-03-31")["corporation_tax_return"]
    assert result["amount_due"] == "0"
    assert "payment_status" not in result
    assert result["payment_due_on"] != result["filing_due_on"]


@pytest.mark.parametrize("amount,status", [("0", None), ("-30", None), ("50", "marked_as_paid"), ("70", "unpaid")])
def test_signed_payment_and_status_are_not_reinterpreted(tax, amount, status):
    invoke, rows, _, _ = tax
    payment = rows[0]["payments"][0]
    payment["amount_due"] = amount
    payment.pop("status")
    if status:
        payment["status"] = status
    result = invoke("list_vat_returns")["vat_returns"][0]["payments"][0]
    assert result["amount_due"] == amount
    assert result.get("status") == status


@pytest.mark.parametrize("code", [403, 404])
def test_unavailable_is_not_an_empty_collection(tax, code):
    invoke, _, _, failure = tax
    failure.append(code)
    with pytest.raises(urllib.error.HTTPError):
        invoke("list_vat_returns")


def test_successful_absence_and_malformed_date_or_user(tax):
    invoke, rows, calls, _ = tax
    rows.clear()
    assert invoke("list_vat_returns") == {"vat_returns": []}
    count = len(calls)
    for name, args in [
        ("get_vat_return", {"period_ends_on": "../company"}),
        ("list_self_assessment_returns", {"user_id": "7/../../company"}),
        ("list_self_assessment_returns", {}),
    ]:
        with pytest.raises(jsonschema.ValidationError):
            invoke(name, **args)
    assert len(calls) == count


def test_reviewed_partial_residual_forecast_handoff(tax):
    invoke, _, _, _ = tax
    result = invoke("list_vat_returns")["vat_returns"][0]
    payment = result["payments"][0]
    # Synthetic user review confirms GBP, business account, 40 already paid and
    # reflected in opening balance, 80 remaining, and no bill/commitment overlap.
    commitment = dict(
        url=result["url"] + "#payment-0", date=payment["due_on"], currency="GBP", amount="-80", additional=True
    )
    data: dict[str, Any] = dict(
        start=date(2026, 5, 1),
        timestamp="2026-05-01T00:00:00Z",
        currency="GBP",
        accounts=[
            dict(
                url=BASE + "bank_accounts/1", current_balance="1000", currency="GBP", latest_activity_date="2026-05-01"
            )
        ],
        invoices=[],
        bills=[],
        commitments=[commitment],
        missing_inputs=[],
    )
    forecast_result = forecast(**data)
    assert forecast_result["weeks"][0]["payments"] == Decimal("80")
    assert forecast_result["weeks"][0]["closing"] == Decimal("920")
    # Unresolved currency/overlap never becomes a complete forecast.
    data["missing_inputs"] = ["Tax currency and overlap review outstanding"]
    assert forecast(**data)["status"] == "incomplete"
    data["missing_inputs"] = []
    data["commitments"] = [commitment, commitment]
    with pytest.raises(ValueError, match="unique"):
        forecast(**data)


def test_tax_audit_is_read_only():
    operations = [
        op
        for op in audit()
        if "tax_return" in op["name"] or "vat_return" in op["name"] or "self_assessment_return" in op["name"]
    ]
    assert len(operations) == 6
    for op in operations:
        assert op["method"] == "GET"
        assert REGISTRY[op["name"]].descriptor.annotations.read_only_hint


@pytest.mark.parametrize(
    "filing", ["unfiled", "pending", "rejected", "provisionally_filed", "filed", "marked_as_filed"]
)
def test_income_tax_period_and_filing_evidence(tax, filing):
    invoke, rows, _, _ = tax
    rows[0].update(
        period_starts_on="2024-04-06", period_ends_on="2025-04-05", filing_status=filing, filing_due_on="2026-01-31"
    )
    rows[0]["payments"] = [
        dict(label="Payment on Account", due_on="2025-01-31", amount_due="100", status="unpaid"),
        dict(label="Balancing Payment", due_on="2026-01-31", amount_due="-50"),
    ]
    record = invoke("get_self_assessment_return", user_id="7", period_ends_on="2025-04-05")["self_assessment_return"]
    assert record["filing_status"] == filing
    assert record["period_starts_on"] == "2024-04-06"
    assert record["period_ends_on"] == "2025-04-05"
    assert [p["due_on"] for p in record["payments"]] == ["2025-01-31", "2026-01-31"]
    assert "status" not in record["payments"][1]
