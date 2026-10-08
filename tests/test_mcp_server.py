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


def test_find_contacts_filters_across_pages(monkeypatch):
    pages = {
        1: [{"organisation_name": "Other"}] * 99 + [{"organisation_name": "Acme Ltd"}],
        2: [{"first_name": "Bob", "email": "ACME@x.com"}, {"organisation_name": None}],
    }
    monkeypatch.setattr(mcp_server, "call", lambda m, path, body=None: {"contacts": pages[int(path[-1])]})
    assert len(mcp_server.find_contacts("acme")) == 2


def test_create_project_and_task_read_back(monkeypatch):
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        return {"project": {"url": BASE + "projects/5"}, "task": {"url": BASE + "tasks/6"}} if method == "POST" else {}

    monkeypatch.setattr(mcp_server, "call", fake)
    mcp_server.create_project(BASE + "contacts/1", "Acme", "GBP", "500", budget="20")
    project = calls[0][2]["project"]
    assert (calls[0][1], project["status"], project["budget_units"]) == ("projects", "Active", "Days")
    assert calls[1][:2] == ("GET", "projects/5")
    mcp_server.create_task(BASE + "projects/5", "Dev", "500")
    assert calls[2][1] == f"tasks?project={BASE}projects/5"
    assert calls[2][2]["task"]["billing_period"] == "day"
    assert calls[3][:2] == ("GET", "tasks/6")


def test_create_contact_posts_only_given_fields_and_reads_back(monkeypatch):
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        return {"contact": {"url": BASE + "contacts/5"}}

    monkeypatch.setattr(mcp_server, "call", fake)
    mcp_server.create_contact(organisation_name="Acme", email="a@x.com", payment_terms_in_days=30)
    assert calls[0][2] == {
        "contact": {"organisation_name": "Acme", "email": "a@x.com", "default_payment_terms_in_days": 30}
    }
    assert calls[1][:2] == ("GET", "contacts/5")
    with pytest.raises(ValueError):
        mcp_server.create_contact(first_name="Bob")


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
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))


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


def test_create_bill_attaches_file_and_reads_back(monkeypatch, tmp_path):
    calls = []

    def fake(method, path, body=None):
        calls.append((method, path, body))
        return {"bill": {"url": BASE + "bills/5"}}

    monkeypatch.setattr(mcp_server, "call", fake)
    pdf = tmp_path / "inv.pdf"
    pdf.write_bytes(b"%PDF")
    items = [{"category": BASE + "categories/285", "description": "Hosting", "total_value": "100.00"}]
    mcp_server.create_bill(BASE + "contacts/1", "INV-1", "2026-10-01", "2026-10-31", items, str(pdf))
    bill = calls[0][2]["bill"]
    assert bill["bill_items"] == items
    assert bill["attachment"] == {"file_name": "inv.pdf", "content_type": "application/pdf", "data": "JVBERg=="}
    assert calls[1][:2] == ("GET", "bills/5")


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


def test_tools_registered_with_hints():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert set(tools) == {
        "freeagent_get",
        "find_contacts",
        "create_contact",
        "create_timeslip",
        "create_draft_invoice",
        "create_expense",
        "create_draft_estimate",
        "create_project",
        "create_task",
        "create_bill",
        "explain_bank_transaction",
    }
    assert tools["freeagent_get"].annotations.read_only_hint
    assert not tools["create_timeslip"].annotations.read_only_hint
