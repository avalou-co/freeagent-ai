import asyncio

import pytest

mcp_server = pytest.importorskip("freeagent_ai.mcp_server", reason="mcp extra not installed")

BASE = "https://api.freeagent.com/v2/"


def test_path_accepts_relative_and_full_urls():
    assert mcp_server._path("users/me") == "users/me"
    assert mcp_server._path(BASE + "projects/1") == "projects/1"


@pytest.mark.parametrize("bad", ["https://evil.example/x", "/v2/users", "../token_endpoint"])
def test_path_rejects_bad_urls(bad):
    with pytest.raises(ValueError):
        mcp_server._path(bad)


def test_draft_invoice_turns_emails_off_and_reads_back(monkeypatch):
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        return {"invoice": {"url": BASE + "invoices/9"}} if method == "POST" else {"invoice": {"status": "Draft"}}

    monkeypatch.setattr(mcp_server, "call", fake)
    out = mcp_server.create_draft_invoice(BASE + "contacts/1", BASE + "projects/2", "2026-10-07", 30)
    inv = calls[0][2]["invoice"]
    assert not (inv["send_new_invoice_emails"] or inv["send_reminder_emails"] or inv["send_thank_you_emails"])
    assert inv["include_timeslips"] == "billed_grouped_by_timeslip"
    assert "invoice_items" not in inv
    assert calls[1][:2] == ("GET", "invoices/9")
    assert out["invoice"]["status"] == "Draft"


def test_explain_bank_transaction_requires_one_target_and_reads_back(monkeypatch):
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        return {"bank_transaction_explanation": {"url": BASE + "bank_transaction_explanations/5"}}

    monkeypatch.setattr(mcp_server, "call", fake)
    args = (BASE + "bank_transactions/1", "2026-10-07", "-12.50")
    for kw in ({}, {"category": "c", "paid_bill": "b"}):
        with pytest.raises(ValueError):
            mcp_server.explain_bank_transaction(*args, **kw)
    assert not calls
    mcp_server.explain_bank_transaction(*args, paid_bill=BASE + "bills/2")
    exp = calls[0][2]["bank_transaction_explanation"]
    assert calls[0][:2] == ("POST", "bank_transaction_explanations")
    assert exp["paid_bill"] == BASE + "bills/2" and "category" not in exp
    assert calls[1][:2] == ("GET", "bank_transaction_explanations/5")


def test_draft_estimate_is_draft_and_reads_back(monkeypatch):
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        return {"estimate": {"url": BASE + "estimates/4"}} if method == "POST" else {"estimate": {"status": "Draft"}}

    monkeypatch.setattr(mcp_server, "call", fake)
    items = [{"description": "Design", "item_type": "Days", "quantity": "2", "price": "400"}]
    out = mcp_server.create_draft_estimate(BASE + "contacts/1", "2026-10-07", items, reference="EST-1")
    est = calls[0][2]["estimate"]
    assert calls[0][:2] == ("POST", "estimates")
    assert est["status"] == "Draft"
    assert est["estimate_items"] == items
    assert est["reference"] == "EST-1"
    assert "project" not in est
    assert "currency" not in est
    assert calls[1][:2] == ("GET", "estimates/4")
    assert out["estimate"]["status"] == "Draft"


def test_tools_registered_with_hints():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert set(tools) == {
        "freeagent_get",
        "create_timeslip",
        "create_draft_invoice",
        "explain_bank_transaction",
        "create_draft_estimate",
    }
    assert tools["freeagent_get"].annotations.read_only_hint
    assert not tools["create_timeslip"].annotations.read_only_hint
