import asyncio
import unittest
from unittest import mock

try:
    from freeagent_ai import mcp_server
except ImportError:  # mcp extra not installed
    mcp_server = None

BASE = "https://api.freeagent.com/v2/"


@unittest.skipIf(mcp_server is None, "mcp extra not installed")
class McpServerTest(unittest.TestCase):
    def test_path_accepts_relative_and_full_urls(self):
        self.assertEqual(mcp_server._path("users/me"), "users/me")
        self.assertEqual(mcp_server._path(BASE + "projects/1"), "projects/1")
        for bad in ("https://evil.example/x", "/v2/users", "../token_endpoint"):
            with self.assertRaises(ValueError):
                mcp_server._path(bad)

    def test_draft_invoice_turns_emails_off_and_reads_back(self):
        calls = []

        def fake(method, path, body=None):
            calls.append((method, path, body))
            return {"invoice": {"url": BASE + "invoices/9"}} if method == "POST" else {"invoice": {"status": "Draft"}}

        with mock.patch.object(mcp_server, "call", fake):
            out = mcp_server.create_draft_invoice(BASE + "contacts/1", BASE + "projects/2", "2026-10-07", 30)
        inv = calls[0][2]["invoice"]
        self.assertFalse(inv["send_new_invoice_emails"] or inv["send_reminder_emails"] or inv["send_thank_you_emails"])
        self.assertEqual(inv["include_timeslips"], "billed_grouped_by_timeslip")
        self.assertNotIn("invoice_items", inv)
        self.assertEqual(calls[1][:2], ("GET", "invoices/9"))
        self.assertEqual(out["invoice"]["status"], "Draft")

    def test_tools_registered_with_hints(self):
        tools = {t.name: t for t in asyncio.run(mcp_server.mcp.list_tools())}
        self.assertEqual(set(tools), {"freeagent_get", "create_timeslip", "create_draft_invoice"})
        self.assertTrue(tools["freeagent_get"].annotations.read_only_hint)
        self.assertFalse(tools["create_timeslip"].annotations.read_only_hint)


if __name__ == "__main__":
    unittest.main()
