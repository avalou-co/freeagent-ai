"""Synthetic authenticated original-context refresh and one-file delegated delivery."""

import base64
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from conftest import settings
from starlette.testclient import TestClient

from freeagent_ai.document_delivery import UI_URI
from freeagent_ai.hosted_accounts import Principal, key_for
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.public_tools import Dispatcher

BASE = "https://api.freeagent.com/v2/"


def synthetic_pdf():
    value = b"%PDF-1.4\n"
    offsets = [0]
    bodies = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Count 1 /Kids [3 0 R] >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>",
    ]
    for index, body in enumerate(bodies, 1):
        offsets.append(len(value))
        value += str(index).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    start = len(value)
    value += b"xref\n0 4\n0000000000 65535 f \n"
    value += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    return value + f"trailer\n<< /Size 4 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()


PDF = synthetic_pdf()


@pytest.fixture
def delivery(accounts):
    now = [time.time()]
    accounts.clock = lambda: now[0]
    auth_time = int(now[0]) - 10
    for subject, company in (("alice", "1"), ("bob", "2")):
        accounts.replace(
            "oauth2|freeagent|" + subject,
            BASE + "company/" + company,
            "production",
            {"access_token": subject, "expires_at": time.time() + 86400},
            0,
        )
    calls, mode = [], {}

    def transport(method, url, deadline, **kwargs):
        subject = kwargs["headers"]["Authorization"].split()[-1]
        calls.append((subject, method, url))
        path = urlsplit(url).path.removeprefix("/v2/")
        if mode.get("disconnect"):
            accounts.disconnect("oauth2|freeagent|" + subject, 1)
        if path.endswith("/pdf"):
            return {"pdf": {"content": mode.get("content", base64.encodebytes(PDF).decode())}}, {}
        root = {"invoices": "invoice", "estimates": "estimate", "credit_notes": "credit_note"}[path.split("/")[0]]
        return {root: {"url": BASE + path, "reference": "INV-007"}}, {}

    dispatcher = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    verifier = SimpleNamespace(
        principal=lambda token: Principal(
            "oauth2|freeagent|" + token,
            frozenset() if token == "denied" else frozenset({"freeagent:read"}),
            auth_time,
            1,
        )
    )
    with TestClient(
        create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN, raise_server_exceptions=False
    ) as client:

        def rpc(method, params=None, subject="alice"):
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + subject, "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            )
            return response.json()["result"]

        def offer(root="invoice"):
            return rpc("tools/call", {"name": "get_" + root + "_pdf", "arguments": {"id": "7"}})

        def refresh(context, root="invoice", subject="alice"):
            return rpc("tools/call", {"name": "refresh_" + root + "_pdf", "arguments": {"context": context}}, subject)

        def grant(root="invoice"):
            context = offer(root)["_meta"]["document_download"]["context"]
            result = refresh(context, root)
            assert not result.get("isError"), result
            return urlsplit(result["_meta"]["document_download"]["url"]).fragment

        def download(token, cookie="", origin=ORIGIN):
            headers = {"Origin": origin, **({"Cookie": "__session=" + cookie} if cookie else {})}
            return client.post("/documents/download", data={"grant": token}, headers=headers)

        yield SimpleNamespace(
            client=client,
            rpc=rpc,
            offer=offer,
            refresh=refresh,
            grant=grant,
            download=download,
            calls=calls,
            mode=mode,
            accounts=accounts,
            now=now,
        )


@pytest.mark.parametrize(
    "root,collection", [("invoice", "invoices"), ("estimate", "estimates"), ("credit_note", "credit_notes")]
)
def test_registered_resource_original_context_private_fresh_grant_and_attachment(delivery, root, collection):
    d = delivery
    resource = d.rpc("resources/read", {"uri": UI_URI})["contents"][0]
    assert UI_URI == "ui://freeagent/document-download-v3.html"
    for tool in d.rpc("tools/list")["tools"]:
        if tool["name"] in {"get_invoice_pdf", "get_estimate_pdf", "get_credit_note_pdf"}:
            assert tool["_meta"]["ui"]["resourceUri"] == UI_URI
    for old_uri in ("ui://freeagent/document-download.html", "ui://freeagent/document-download-v2.html"):
        assert (
            "error"
            in d.client.post(
                "/mcp",
                headers={"Authorization": "Bearer alice", "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": "resources/read", "params": {"uri": old_uri}},
            ).json()
        )
    assert resource["mimeType"] == "text/html;profile=mcp-app"
    assert resource["_meta"]["openai/widgetCSP"]["redirect_domains"] == [ORIGIN]
    offer = d.offer(root)
    private = offer["_meta"]["document_download"]
    context = private["context"]
    assert "url" not in private
    assert context not in json.dumps(offer["structuredContent"]) + json.dumps(offer["content"])
    assert offer["structuredContent"]["document_label"].endswith("INV-007")
    refreshed = d.refresh(context, root)
    token = urlsplit(refreshed["_meta"]["document_download"]["url"]).fragment
    assert token not in json.dumps(refreshed["structuredContent"]) + json.dumps(refreshed["content"])
    state = d.accounts.store.get("web_state", key_for(token))
    assert not any(key in state for key in ("data", "content", "bytes", "pdf", "access_token"))
    response = d.download(token)
    assert response.status_code == 200 and response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="{collection}-7.pdf"'
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert d.download(token).status_code == 400


@pytest.mark.parametrize("elapsed", [121, 4 * 3600])
def test_stale_card_refreshes_within_original_connected_session_without_user_loop(delivery, elapsed):
    d = delivery
    context = d.offer()["_meta"]["document_download"]["context"]
    d.now[0] += elapsed
    refreshed = d.refresh(context)
    assert not refreshed.get("isError")
    token = urlsplit(refreshed["_meta"]["document_download"]["url"]).fragment
    assert d.download(token).status_code == 200


@pytest.mark.parametrize("cookie", ["", "unrelated-browser-account", "expired-browser-session"])
def test_capability_ignores_browser_cookie_and_uses_only_original_provider_credentials(delivery, cookie):
    d = delivery
    token = d.grant()
    before = len(d.calls)
    assert d.download(token, cookie).status_code == 200
    assert {subject for subject, _, _ in d.calls[before:]} == {"alice"}


@pytest.mark.parametrize(
    "refusal", ["wrong_origin", "expired", "disconnected", "relinked", "oversized", "malformed", "provider_malformed"]
)
def test_delegated_download_refusals_do_not_deliver_or_rebind(delivery, refusal):
    d = delivery
    token = d.grant()
    before = len(d.calls)
    if refusal == "expired":
        d.now[0] += 121
    if refusal == "disconnected":
        d.accounts.disconnect("oauth2|freeagent|alice", 1)
    if refusal == "relinked":
        d.accounts.replace(
            "oauth2|freeagent|alice", BASE + "company/99", "production", {"access_token": "replacement"}, 1
        )
    if refusal == "oversized":
        token = "x" * 1024
    if refusal == "malformed":
        token = "bad"
    if refusal == "provider_malformed":
        d.mode["content"] = "private malformed content"
    response = d.download(token, origin="https://evil.invalid" if refusal == "wrong_origin" else ORIGIN)
    assert response.status_code != 200
    assert token not in response.text and "private malformed content" not in response.text
    if refusal != "provider_malformed":
        assert len(d.calls) == before


@pytest.mark.parametrize(
    "refusal",
    ["other_principal", "denied_scope", "relinked", "disconnect", "wrong_type", "tampered", "expired_context"],
)
def test_refresh_requires_exact_immutable_original_mcp_context_before_provider(delivery, refusal):
    d = delivery
    context = d.offer()["_meta"]["document_download"]["context"]
    if refusal == "relinked":
        d.accounts.replace(
            "oauth2|freeagent|alice", BASE + "company/99", "production", {"access_token": "replacement"}, 1
        )
    if refusal == "disconnect":
        d.accounts.disconnect("oauth2|freeagent|alice", 1)
    if refusal == "tampered":
        context = "x" * 43
    if refusal == "expired_context":
        d.now[0] += 31 * 86400
    before = len(d.calls)
    result = d.refresh(
        context,
        "estimate" if refusal == "wrong_type" else "invoice",
        "bob" if refusal == "other_principal" else "denied" if refusal == "denied_scope" else "alice",
    )
    assert result["isError"]
    assert len(d.calls) == before
    assert context not in json.dumps(result)


def test_refresh_only_authorizes_original_context_without_slow_provider_fetch(delivery):
    d = delivery
    context = d.offer()["_meta"]["document_download"]["context"]
    before = len(d.calls)
    refreshed = d.refresh(context)
    assert not refreshed.get("isError")
    assert len(d.calls) == before
    assert (
        refreshed["structuredContent"]["collected_at"]
        == d.accounts.store.get("web_state", key_for(context))["metadata"]["collected_at"]
    )


def test_disconnect_during_download_prevents_byte_release(delivery):
    d = delivery
    token = d.grant()
    d.mode["disconnect"] = True
    assert d.download(token).status_code != 200
    assert d.download(token).status_code != 200


def test_concurrent_redemption_has_one_winner_and_no_duplicate_provider_fetch(delivery):
    d = delivery
    token = d.grant()
    before = len(d.calls)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: d.download(token).status_code, range(2)))
    assert sorted(results) == [200, 400]
    assert len(d.calls) - before == 2


def test_refresh_is_ui_only_and_cannot_recursively_render_a_new_card(delivery):
    tools = {item["name"]: item for item in delivery.rpc("tools/list")["tools"]}
    for name in ("refresh_invoice_pdf", "refresh_estimate_pdf", "refresh_credit_note_pdf"):
        meta = tools[name]["_meta"]
        assert meta["ui"] == {"visibility": ["app"]}
        assert "openai/outputTemplate" not in meta


def test_publication_remains_blocked_until_reviewed_installed_client_acceptance(tmp_path):
    from freeagent_ai.public_package import build

    with pytest.raises(ValueError, match="Installed web/mobile document delivery acceptance pending"):
        build(
            Path(__file__).resolve().parents[1],
            tmp_path / "release.zip",
            metadata={"mcp_client_id": "synthetic", "evidence": {"mobile_verified": True}},
        )


def test_context_without_snapshot_fails_closed_without_provider_fetch(delivery):
    d = delivery
    context = d.offer()["_meta"]["document_download"]["context"]
    record = d.accounts.store.get("web_state", key_for(context))
    record.pop("metadata")
    d.accounts.store.mutate("web_state", key_for(context), lambda _: record)
    before = len(d.calls)
    result = d.refresh(context)
    assert result["isError"]
    assert len(d.calls) == before
    assert "document_download" not in result.get("_meta", {})
