"""Real hosted resource/attachment contract with synthetic provider and identities."""

import base64
import json
import time
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


# Small valid PDF: two objects, cross-reference table and trailer.
def synthetic_pdf():
    value = b"%PDF-1.4\n"
    offsets = [0]
    for index, body in enumerate([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Count 0 /Kids [] >>"], 1):
        offsets.append(len(value))
        value += str(index).encode() + b" 0 obj\n" + body + b"\nendobj\n"
    start = len(value)
    value += b"xref\n0 3\n0000000000 65535 f \n"
    value += b"".join(f"{offset:010} 00000 n \n".encode() for offset in offsets[1:])
    return value + f"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()


PDF = synthetic_pdf()


@pytest.fixture
def delivery(accounts):
    now = [time.time()]
    accounts.clock = lambda: now[0]
    # Real federated authentication precedes /connect/complete account replacement.
    auth_time = int(now[0]) - 10
    cookies = {}
    for subject, company in (("alice", "1"), ("bob", "2")):
        accounts.replace(
            "oauth2|freeagent|" + subject,
            BASE + "company/" + company,
            "production",
            {"access_token": subject, "expires_at": time.time() + 3600},
            0,
        )
        cookies[subject] = accounts.new_state(
            "session",
            {"subject": "oauth2|freeagent|" + subject, "primary_auth_time": auth_time, "connection_generation": 1},
            ttl=3600,
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
        return {root: {"url": BASE + path}}, {}

    dispatcher = Dispatcher(
        accounts, "id", "secret", client_factory=lambda *args: HostedClient(*args, transport=transport)
    )
    verifier = SimpleNamespace(
        principal=lambda token: Principal("oauth2|freeagent|" + token, frozenset({"freeagent:read"}), auth_time, 1)
    )
    with TestClient(
        create_app(settings(), accounts, verifier, dispatcher), base_url=ORIGIN, raise_server_exceptions=False
    ) as client:

        def rpc(method, params=None):
            response = client.post(
                "/mcp",
                headers={"Authorization": "Bearer alice", "Accept": "application/json, text/event-stream"},
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
            )
            return response.json()["result"]

        def offer(root="invoice"):
            return rpc("tools/call", {"name": "get_" + root + "_pdf", "arguments": {"id": "7"}})

        def download(token, subject="alice", origin=ORIGIN):
            headers = {"Origin": origin, "Cookie": "__session=" + cookies[subject]} if subject else {"Origin": origin}
            return client.post("/documents/download", data={"grant": token}, headers=headers)

        yield SimpleNamespace(
            client=client,
            rpc=rpc,
            offer=offer,
            download=download,
            cookies=cookies,
            verifier=verifier,
            calls=calls,
            mode=mode,
            accounts=accounts,
            now=now,
        )


@pytest.mark.parametrize(
    "root,collection", [("invoice", "invoices"), ("estimate", "estimates"), ("credit_note", "credit_notes")]
)
def test_registered_resource_and_authenticated_attachment(delivery, root, collection):
    d = delivery
    resources = d.rpc("resources/list")["resources"]
    assert {item["uri"] for item in resources} == {UI_URI}
    resource = d.rpc("resources/read", {"uri": UI_URI})["contents"][0]
    assert resource["mimeType"] == "text/html;profile=mcp-app"
    assert resource["_meta"]["openai/widgetCSP"]["redirect_domains"] == [ORIGIN]
    result = d.offer(root)
    assert not result.get("isError")
    token = urlsplit(result["_meta"]["document_download"]["url"]).fragment
    assert token not in json.dumps(result["structuredContent"]) + json.dumps(result["content"])
    assert "blob" not in json.dumps(result)
    state = d.accounts.store.get("web_state", key_for(token))
    assert not any(key in state for key in ("data", "content", "bytes", "pdf", "access_token"))
    response = d.download(token)
    assert response.status_code == 200
    assert response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"] == f'attachment; filename="{collection}-7.pdf"'
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert d.download(token).status_code == 400


@pytest.mark.parametrize(
    "refusal",
    [
        "wrong_account",
        "missing_cookie",
        "wrong_origin",
        "expired",
        "disconnected",
        "relinked",
        "oversized",
        "malformed",
        "provider_malformed",
    ],
)
def test_download_refusals_do_not_deliver_or_rebind(delivery, refusal):
    d = delivery
    token = urlsplit(d.offer()["_meta"]["document_download"]["url"]).fragment
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
    response = d.download(
        token,
        "bob" if refusal == "wrong_account" else ("" if refusal == "missing_cookie" else "alice"),
        "https://evil.invalid" if refusal == "wrong_origin" else ORIGIN,
    )
    assert response.status_code != 200
    assert response.headers["content-type"].startswith("text/plain")
    assert token not in response.text
    assert "private malformed content" not in response.text
    if refusal != "provider_malformed":
        assert len(d.calls) == before


def test_disconnect_during_download_prevents_byte_release(delivery):
    d = delivery
    token = urlsplit(d.offer()["_meta"]["document_download"]["url"]).fragment
    d.mode["disconnect"] = True
    assert d.download(token).status_code != 200
    assert d.download(token).status_code != 200


def test_publication_remains_blocked_until_reviewed_installed_client_acceptance(tmp_path):
    from pathlib import Path

    from freeagent_ai.public_package import build

    with pytest.raises(ValueError, match="Installed web/mobile document delivery acceptance pending"):
        build(
            Path(__file__).resolve().parents[1],
            tmp_path / "release.zip",
            metadata={"mcp_client_id": "synthetic", "evidence": {"mobile_verified": True}},
        )
    assert not (tmp_path / "release.zip").exists()


def test_concurrent_redemption_has_one_winner_and_no_duplicate_provider_fetch(delivery):
    from concurrent.futures import ThreadPoolExecutor

    d = delivery
    token = urlsplit(d.offer()["_meta"]["document_download"]["url"]).fragment
    before = len(d.calls)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: d.download(token).status_code, range(2)))
    assert sorted(results) == [200, 400]
    assert len(d.calls) - before == 2  # One record identity read and one PDF read.


@pytest.mark.parametrize("generation", [1, None, 2, True, 0, "1"])
def test_browser_callback_persists_signed_generation_and_uses_real_auth_order(delivery, monkeypatch, generation):
    from urllib.parse import parse_qs

    import jwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from freeagent_ai.hosted_auth import GENERATION_CLAIM, PRIMARY_AUTH_CLAIM, Verifier

    d = delivery
    offer_token = urlsplit(d.offer()["_meta"]["document_download"]["url"]).fragment
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verified = Verifier(
        settings(), SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=private.public_key()))
    )
    # /auth/callback exercises actual JWT signature/audience/issuer validation,
    # not a fabricated session record or future primary authentication timestamp.
    d.verifier.claims = verified.claims
    response = d.client.get("/login", follow_redirects=False)
    params = parse_qs(urlsplit(response.headers["location"]).query)
    now = int(time.time())
    claims = {
        "iss": settings().issuer,
        "aud": settings().web_client_id,
        "sub": "oauth2|freeagent|alice",
        "iat": now,
        "exp": now + 600,
        "nonce": params["nonce"][0],
        PRIMARY_AUTH_CLAIM: now - 10,
    }
    if generation is not None:
        claims[GENERATION_CLAIM] = generation
    signed = jwt.encode(claims, private, algorithm="RS256")
    monkeypatch.setattr("freeagent_ai.hosted_app.request_json", lambda *_args, **_kwargs: ({"id_token": signed}, {}))
    callback = d.client.get(
        "/auth/callback", params={"state": params["state"][0], "code": "synthetic-code"}, follow_redirects=False
    )
    if type(generation) is not int or generation < 1:
        assert callback.status_code == 400
        return
    assert callback.status_code == 307
    d.cookies["alice"] = d.client.cookies.get("__session")
    session_record = d.accounts.store.get("web_state", key_for(d.cookies["alice"]))
    assert session_record["connection_generation"] == generation
    assert session_record["primary_auth_time"] == now - 10
    link_record = d.accounts.store.get("account_links", key_for("oauth2|freeagent|alice"))
    assert session_record["primary_auth_time"] <= link_record["revoked_before"]
    before = len(d.calls)
    result = d.download(offer_token)
    if generation == 1:
        assert result.status_code == 200 and result.content == PDF
    else:
        assert result.status_code == 400
        assert len(d.calls) == before


@pytest.mark.parametrize("generation", [None, 2, True])
def test_federated_browser_session_missing_or_stale_generation_fails(delivery, generation):
    d = delivery
    token = urlsplit(d.offer()["_meta"]["document_download"]["url"]).fragment
    d.accounts.store.mutate(
        "web_state", key_for(d.cookies["alice"]), lambda record: {**record, "connection_generation": generation}
    )
    before = len(d.calls)
    assert d.download(token).status_code == 400
    assert len(d.calls) == before
