"""Actual connect browser/confidential hops -> signed MCP -> authenticated file."""

import base64
import secrets
import time
from dataclasses import replace
from types import SimpleNamespace
from urllib.parse import urlsplit

import jwt
import pytest
from conftest import settings
from cryptography.hazmat.primitives.asymmetric import rsa
from starlette.testclient import TestClient
from test_document_delivery import PDF
from test_hosted_connect import complete, profile

from freeagent_ai.hosted_accounts import Accounts, MemoryStore, TokenCipher, key_for
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import GENERATION_CLAIM, ORIGIN, PRIMARY_AUTH_CLAIM, Verifier
from freeagent_ai.hosted_client import HostedClient
from freeagent_ai.hosted_connect import COOKIE
from freeagent_ai.public_tools import Dispatcher

BASE = "https://api.freeagent.com/v2/"


@pytest.fixture
def connected_delivery(monkeypatch):
    clock = [time.time()]
    accounts = Accounts(
        MemoryStore(),
        TokenCipher({"1": base64.b64encode(secrets.token_bytes(32)).decode()}, "1"),
        clock=lambda: clock[0],
    )
    config = replace(settings(), connection_secret="synthetic-bridge-secret")
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier = Verifier(
        config, SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
    )
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append(("alice", method, url))
        if url.endswith("token_endpoint"):
            return {"access_token": "synthetic-upstream", "refresh_token": "synthetic-refresh", "expires_in": 3600}, {}
        if url.endswith("users/me"):
            return {"user": {"url": BASE + "users/123"}}, {}
        if url.endswith("company"):
            return {"company": {"url": BASE + "company", "id": "456"}}, {}
        if url.endswith("/pdf"):
            return {"pdf": {"content": base64.encodebytes(PDF).decode()}}, {}
        if "/invoices/" in url:
            return {"invoice": {"url": url}}, {}
        pytest.fail("Unexpected provider route")

    monkeypatch.setattr("freeagent_ai.hosted_connect.request_json", transport)
    dispatcher = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    with TestClient(
        create_app(config, accounts, verifier, dispatcher), base_url=ORIGIN, follow_redirects=False
    ) as client:
        info = profile(client, config)
        pending = client.cookies.get(COOKIE)
        assert accounts.store.get("web_state", key_for(pending))["kind"] == "pending_document_session"
        # Upstream authentication genuinely precedes the confidential account commit.
        clock[0] += 1
        linked = complete(client, config, info)
        assert linked.status_code == 200
        subject = "oauth2|freeagent|" + info["user_id"]
        session = accounts.store.get("web_state", key_for(pending))
        assert session["kind"] == "session"
        assert session["connection_generation"] == linked.json()["generation"]
        assert session["primary_auth_time"] <= accounts.store.get("account_links", key_for(subject))["revoked_before"]
        now = int(time.time())
        token = jwt.encode(
            {
                "iss": config.issuer,
                "aud": ORIGIN + "/mcp",
                "sub": subject,
                "iat": now,
                "exp": now + 600,
                "azp": config.mcp_client_id,
                "scope": "freeagent:read",
                PRIMARY_AUTH_CLAIM: linked.json()["authenticated_at"],
                GENERATION_CLAIM: linked.json()["generation"],
            },
            private,
            algorithm="RS256",
        )

        def rpc(method, params=None):
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer " + token, "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            )
            assert response.status_code == 200
            return response.json()["result"]

        def offer():
            return rpc("tools/call", {"name": "get_invoice_pdf", "arguments": {"id": "7"}})

        yield SimpleNamespace(
            client=client, accounts=accounts, rpc=rpc, offer=offer, cookies={"alice": pending}, calls=calls
        )


def test_full_connect_hops_signed_mcp_offer_and_same_generation_browser_download(connected_delivery):
    d = connected_delivery
    result = d.offer()
    assert not result.get("isError")
    token = urlsplit(result["_meta"]["document_download"]["url"]).fragment
    response = d.client.post("/documents/download", data={"grant": token}, headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-disposition"] == 'attachment; filename="invoices-7.pdf"'
