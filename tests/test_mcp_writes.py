"""The generic MCP tools pass accounting validation through to FreeAgent."""

import asyncio
import copy
import json
import urllib.error
from email.message import Message
from io import BytesIO

import pytest

mcp_server = pytest.importorskip("freeagent_ai.mcp_server")
ToolError = mcp_server.ToolError
BASE = mcp_server.BASE


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_raw_requests_and_responses_are_preserved(monkeypatch, method):
    calls = []
    body = {"invoice": {"status": "Open", "send_new_invoice_emails": True, "new_api_field": {"value": "anything"}}}
    before = copy.deepcopy(body)
    response = {"invoice": {"url": BASE + "invoices/1"}} if method == "POST" else 200

    def api(verb, path, payload=None):
        calls.append((verb, path, payload))
        return response

    monkeypatch.setattr(mcp_server, "call", api)
    if method == "DELETE":
        result = mcp_server.freeagent_delete(BASE + "invoices/1", True)
    else:
        result = getattr(mcp_server, f"freeagent_{method.lower()}")(BASE + "invoices/1", body, True)
    assert result == response
    assert calls == [(method, "invoices/1", None if method == "DELETE" else body)]
    assert body == before


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE"])
def test_approval_is_required_before_api_call(monkeypatch, method):
    calls = []
    monkeypatch.setattr(mcp_server, "call", lambda *args: calls.append(args))
    with pytest.raises(ToolError, match="confirmation"):
        if method == "DELETE":
            mcp_server.freeagent_delete("invoices/1", False)
        else:
            getattr(mcp_server, f"freeagent_{method.lower()}")("invoices/1", {}, False)
    assert not calls


def test_validation_errors_come_from_freeagent_and_are_not_retried(monkeypatch):
    calls = []
    errors = {"errors": [{"message": "Date is invalid"}]}

    def api(*args):
        calls.append(args)
        raise urllib.error.HTTPError(
            BASE + "timeslips/1", 422, "Validation failed", Message(), BytesIO(json.dumps(errors).encode())
        )

    monkeypatch.setattr(mcp_server, "call", api)
    with pytest.raises(ToolError, match="FreeAgent HTTP 422.*Date is invalid"):
        mcp_server.freeagent_put("timeslips/1", {"timeslip": {"dated_on": "invalid"}}, True)
    assert len(calls) == 1


def test_get_exposes_http_status_for_deletion_readback(monkeypatch):
    def api(*args, **kwargs):
        raise urllib.error.HTTPError(BASE + "invoices/1", 404, "Not found", Message(), None)

    monkeypatch.setattr(mcp_server, "call", api)
    with pytest.raises(ToolError, match="FreeAgent HTTP 404"):
        mcp_server.freeagent_get("invoices/1")


def test_authentication_response_is_not_exposed(monkeypatch):
    def api(*args):
        raise urllib.error.HTTPError(
            BASE + "invoices/1", 401, "Unauthorized", Message(), BytesIO(b'{"errors":"private auth detail"}')
        )

    monkeypatch.setattr(mcp_server, "call", api)
    with pytest.raises(ToolError) as caught:
        mcp_server.freeagent_delete("invoices/1", True)
    assert str(caught.value) == "FreeAgent HTTP 401"


def test_timeout_is_not_retried(monkeypatch):
    calls = []

    def api(*args):
        calls.append(args)
        raise TimeoutError("unknown outcome")

    monkeypatch.setattr(mcp_server, "call", api)
    with pytest.raises(TimeoutError):
        mcp_server.freeagent_delete("invoices/1", True)
    assert len(calls) == 1


def test_real_mcp_transport_passes_write_payload_and_provider_error(monkeypatch):
    from mcp.client import Client
    from mcp.client._memory import InMemoryTransport

    calls = []

    def api(method, path, body=None):
        calls.append((method, path, body))
        if path == "timeslips/1":
            raise urllib.error.HTTPError(
                BASE + path, 422, "Validation failed", Message(), BytesIO(b'{"errors":[{"message":"Invalid date"}]}')
            )
        return 200

    monkeypatch.setattr(mcp_server, "call", api)

    async def scenario():
        async with Client(InMemoryTransport(mcp_server.mcp)) as client:
            body = {"invoice": {"send_new_invoice_emails": True, "new_field": "value"}}
            result = await client.call_tool("freeagent_put", {"path": "invoices/1", "body": body, "confirmed": True})
            assert not result.is_error
            assert calls[-1] == ("PUT", "invoices/1", body)
            rejected = await client.call_tool(
                "freeagent_put",
                {"path": "timeslips/1", "body": {"timeslip": {"dated_on": "invalid"}}, "confirmed": True},
            )
            assert rejected.is_error
            assert rejected.content[0].type == "text"
            assert "Invalid date" in rejected.content[0].text

    asyncio.run(scenario())


def test_api_query_can_include_resource_urls(monkeypatch):
    calls = []

    def api(method, path, body=None, **kwargs):
        calls.append((method, path))
        return {"projects": []}

    monkeypatch.setattr(mcp_server, "call", api)
    path = "projects?contact=" + BASE + "contacts/1"
    mcp_server.freeagent_get(path)
    assert calls == [("GET", path)]


@pytest.mark.parametrize(
    "path", ["https://evil.example/invoices/1", "//evil.example/invoices/1", "invoices/%2e%2e/1", "../invoices/1"]
)
def test_generic_write_paths_cannot_change_origin_or_traverse(monkeypatch, path):
    calls = []
    monkeypatch.setattr(mcp_server, "call", lambda *args: calls.append(args))
    with pytest.raises(ValueError):
        mcp_server.freeagent_put(path, {}, True)
    assert not calls
