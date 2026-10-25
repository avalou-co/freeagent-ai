"""Receipt API mechanics, not an evaluation of assistant document interpretation."""

import time

import pytest
from mcp.types import TextContent

from freeagent_ai.hosted_accounts import AccessDenied, Principal
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.public_tools import Dispatcher

BASE = "https://api.freeagent.com/v2/"


@pytest.fixture
def receipt_account(accounts):
    accounts.replace(
        "receipt-reviewer",
        BASE + "company/1",
        "production",
        {"access_token": "synthetic", "expires_at": time.time() + 3600},
        0,
    )
    return Principal("receipt-reviewer", frozenset({"freeagent:read", "freeagent:write"}), 101)


def dispatcher(accounts, transport):
    return Dispatcher(accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport))


@pytest.mark.parametrize("operation,args", [("list_expenses", {}), ("get_expense", {"id": "91"})])
def test_receipt_reference_and_tax_evidence_survive_hosted_reads(
    accounts, receipt_account, hosted_context, operation, args
):
    record = {
        "url": BASE + "expenses/91",
        "receipt_reference": "R-TEST-22",
        "gross_value": "-60.00",
        "currency": "EUR",
        "sales_tax_value": "-10.00",
        "native_gross_value": "-51.00",
        "native_sales_tax_value": "-8.50",
        "manual_sales_tax_amount": "-8.50",
        "sales_tax_status": "TAXABLE",
        "second_sales_tax_rate": "0.0",
        "second_sales_tax_status": "EXEMPT",
    }

    def transport(*_, **__):
        response = {"expenses": [record]} if operation == "list_expenses" else {"expense": record}
        return response, {}

    with hosted_context(receipt_account):
        result = dispatcher(accounts, transport).invoke(operation, args)
    assert result == ({"expenses": [record]} if operation == "list_expenses" else {"expense": record})


@pytest.mark.parametrize("kind", ["expense", "bill"])
@pytest.mark.parametrize("outcome", ["approved", "refused", "failed_readback"])
def test_receipt_attachment_create_and_readback(accounts, receipt_account, hosted_context, monkeypatch, kind, outcome):
    calls = []
    downloads = []
    attachment = {"file_name": "synthetic.pdf", "content_type": "application/x-pdf", "data": "JVBERi0="}
    file = {"download_url": "https://files.example/synthetic", "file_id": "file-synthetic"}

    def download(reference, *_):
        downloads.append(reference)
        return attachment

    monkeypatch.setattr("freeagent_ai.public_tools.download", download)
    record = {
        "url": BASE + kind + "s/91",
        "currency": "EUR",
        "attachment": {"file_name": "synthetic.pdf", "content_type": "application/x-pdf", "file_size": 5},
    }
    if kind == "expense":
        record.update(receipt_reference="R-TEST-22", gross_value="-60.00")
        args = {
            "user": "1",
            "category": "285",
            "dated_on": "2026-10-02",
            "gross_value": "-60.00",
            "description": "Example Travel",
            "receipt": file,
        }
    else:
        record.update(reference="INV-TEST-21", total_value="60.00")
        args = {
            "contact": "1",
            "reference": "INV-TEST-21",
            "dated_on": "2026-10-02",
            "due_on": "2026-11-01",
            "items": [{"category": BASE + "categories/285", "total_value": "60.00"}],
            "attachment": file,
        }
    args.update(currency="EUR", confirmed=outcome != "refused")

    def transport(method, url, deadline, **kwargs):
        calls.append((method, kwargs.get("body")))
        if method == "GET" and outcome == "failed_readback":
            raise TimeoutError()
        return {kind: record}, {}

    client = dispatcher(accounts, transport)
    with hosted_context(receipt_account):
        if outcome == "refused":
            with pytest.raises(AccessDenied):
                client.invoke("create_" + kind, args)
            assert downloads == calls == []
            return
        if outcome == "failed_readback":
            result = client.call_tool("create_" + kind, args)
            assert result.is_error
            assert isinstance(result.content[0], TextContent)
            assert kind + "s/91" in result.content[0].text
            assert "readback was not verified" in result.content[0].text
        else:
            assert client.invoke("create_" + kind, args) == {kind: record}
    assert downloads == [file]
    assert [method for method, _ in calls] == ["POST", "GET"]
    assert calls[0][1][kind]["attachment"] == attachment
    assert calls[0][1][kind]["currency"] == "EUR"
