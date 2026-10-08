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


def test_expense_attaches_receipt_and_reads_back(monkeypatch, tmp_path):
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        return {"expense": {"url": BASE + "expenses/5"}}

    monkeypatch.setattr(mcp_server, "call", fake)
    receipt = tmp_path / "r.pdf"
    receipt.write_bytes(b"%PDF")
    mcp_server.create_expense(
        BASE + "users/1", BASE + "categories/285", "2026-10-07", "-12.50", "Train", "20.0", str(receipt)
    )
    exp = calls[0][2]["expense"]
    assert exp["attachment"] == {"file_name": "r.pdf", "content_type": "application/pdf", "data": "JVBERg=="}
    assert exp["sales_tax_rate"] == "20.0"
    assert calls[1][:2] == ("GET", "expenses/5")


def test_expense_rejects_other_receipt_types(tmp_path):
    bad = tmp_path / "x.exe"
    bad.write_bytes(b"x")
    with pytest.raises(ValueError):
        mcp_server.create_expense("u", "c", "2026-10-07", "-1", "d", receipt_path=str(bad))


def test_tools_registered_with_hints():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert set(tools) == {"freeagent_get", "create_timeslip", "create_draft_invoice", "create_expense"}
    assert tools["freeagent_get"].annotations.read_only_hint
    assert not tools["create_timeslip"].annotations.read_only_hint
