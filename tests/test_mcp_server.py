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


def test_tools_registered_with_hints():
    tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
    assert set(tools) == {"freeagent_get", "find_contacts", "create_contact", "create_timeslip", "create_draft_invoice"}
    assert tools["freeagent_get"].annotations.read_only_hint
    assert not tools["create_timeslip"].annotations.read_only_hint
