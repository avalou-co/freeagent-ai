"""Exercise the browser and both confidential server hops, without live accounts."""

import base64
import hashlib
import secrets
import time
from dataclasses import replace
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import settings
from starlette.testclient import TestClient

from freeagent_ai.hosted_accounts import AccessDenied, Accounts, MemoryStore, Principal, TokenCipher, key_for
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN
from freeagent_ai.hosted_connect import BRIDGE_CLIENT, COOKIE


@pytest.fixture
def flow(monkeypatch):
    accounts = Accounts(MemoryStore(), TokenCipher({"1": base64.b64encode(secrets.token_bytes(32)).decode()}, "1"))
    config = replace(settings(), connection_secret="synthetic-bridge-secret")
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append((method, url))
        if url.endswith("token_endpoint"):
            return {"access_token": "upstream-private", "refresh_token": "upstream-refresh", "expires_in": 3600}, {}
        if url.endswith("users/me"):
            return {"user": {"url": "https://api.freeagent.com/v2/users/123"}}, {}
        if url.endswith("company"):
            return {"company": {"url": "https://api.freeagent.com/v2/company", "id": "456"}}, {}
        pytest.fail("Unexpected upstream call")

    monkeypatch.setattr("freeagent_ai.hosted_connect.request_json", transport)
    app = create_app(config, accounts, verifier=object())
    with TestClient(app, base_url=ORIGIN, follow_redirects=False) as client:
        yield client, accounts, config, calls


def headers(config):
    return {
        "Authorization": "Basic " + base64.b64encode(f"{BRIDGE_CLIENT}:{config.connection_secret}".encode()).decode()
    }


def authorize(client, config):
    verifier = "a" * 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    params = {
        "client_id": BRIDGE_CLIENT,
        "response_type": "code",
        "redirect_uri": config.issuer + "login/callback",
        "state": "auth0-transaction",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    response = client.get("/connect/authorize", params=params)
    assert response.status_code == 307
    location = urlsplit(response.headers["location"])
    assert location.hostname == "api.freeagent.com"
    q = parse_qs(location.query)
    assert q["redirect_uri"] == [ORIGIN + "/freeagent/callback"]
    return q["state"][0], verifier, params


def profile(client, config):
    state, verifier, _ = authorize(client, config)
    callback = client.get("/freeagent/callback", params={"state": state, "code": "upstream-code"})
    assert callback.status_code == 307
    q = parse_qs(urlsplit(callback.headers["location"]).query)
    assert q["state"] == ["auth0-transaction"]
    assert urlsplit(callback.headers["location"]).hostname == "example.auth0.com"
    form = {
        "grant_type": "authorization_code",
        "code": q["code"][0],
        "redirect_uri": config.issuer + "login/callback",
        "code_verifier": verifier,
    }
    denied = client.post("/connect/token", data=form)
    assert denied.status_code == 400
    bad_verifier = client.post("/connect/token", data={**form, "code_verifier": "b" * 43}, headers=headers(config))
    assert bad_verifier.status_code == 400
    response = client.post(
        "/connect/token", data={**form, "client_id": BRIDGE_CLIENT, "client_secret": config.connection_secret}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert "upstream" not in response.text
    assert client.post("/connect/token", data=form, headers=headers(config)).status_code == 400
    auth = {"Authorization": "Bearer " + token}
    response = client.get("/connect/profile", headers=auth)
    assert response.status_code == 200
    assert "upstream" not in response.text
    assert client.get("/connect/profile", headers=auth).status_code == 400
    return response.json()


def complete(client, config, info, subject=None):
    subject = subject or "oauth2|freeagent|" + info["user_id"]
    return client.post(
        "/connect/complete",
        data={"subject": subject, "receipt": info["app_metadata"]["freeagent_login_receipt"]},
        headers=headers(config),
    )


def test_first_connection_returns_to_auth0_already_linked_without_signup(flow):
    client, accounts, config, calls = flow
    info = profile(client, config)
    subject = "oauth2|freeagent|" + info["user_id"]
    assert complete(client, config, info, "oauth2|freeagent|wrong").status_code == 400
    assert not accounts.store.get("account_links", key_for(subject))
    response = complete(client, config, info)
    assert response.status_code == 200
    generation = response.json()["generation"]
    principal = Principal(subject, frozenset({"freeagent:read"}), response.json()["authenticated_at"], generation)
    binding = accounts.bind(principal)
    assert accounts.credentials(binding)["access_token"] == "upstream-private"
    assert complete(client, config, info).status_code == 400
    assert len(calls) == 3
    for row in accounts.store.records.values():
        assert "upstream-private" not in str(row)


def test_reconnect_and_disconnect_never_revive_old_tokens(flow):
    client, accounts, config, _ = flow
    first = complete(client, config, profile(client, config)).json()
    identity = hashlib.sha256(b"production|456|https://api.freeagent.com/v2/users/123").hexdigest()
    subject = "oauth2|freeagent|" + identity
    old = Principal(subject, frozenset(), first["authenticated_at"], first["generation"])
    binding = accounts.bind(old)
    second = complete(client, config, profile(client, config)).json()
    assert second["generation"] == first["generation"] + 1
    with pytest.raises(AccessDenied):
        accounts.bind(old)
    with pytest.raises(AccessDenied):
        accounts.credentials(binding)
    fresh = Principal(subject, frozenset(), second["authenticated_at"], second["generation"])
    accounts.disconnect(subject, second["generation"])
    with pytest.raises(AccessDenied):
        accounts.bind(fresh)


def test_browser_mismatch_denial_replay_and_expiry(flow):
    client, accounts, config, calls = flow
    state, _, _ = authorize(client, config)
    browser = client.cookies.get(COOKIE)
    client.cookies.clear()
    assert client.get("/freeagent/callback", params={"state": state, "code": "x"}).status_code == 400
    assert calls == []
    client.cookies.set(COOKIE, browser, domain="freeagent-ai.avalou.co", path="/")
    denied = client.get("/freeagent/callback", params={"state": state, "error": "access_denied"})
    assert denied.status_code == 307 and "error=access_denied" in denied.headers["location"]
    assert client.get("/freeagent/callback", params={"state": state, "code": "x"}).status_code == 400
    assert calls == []
    info = profile(client, config)
    accounts.clock = lambda: time.time() + 121
    assert complete(client, config, info).status_code == 400


def test_redirect_and_pkce_are_exact(flow):
    client, _, config, _ = flow
    _, _, params = authorize(client, config)
    for change in [
        {"redirect_uri": "https://attacker.invalid/callback"},
        {"client_id": "other"},
        {"code_challenge_method": "plain"},
        {"code_challenge": "short"},
        {"state": ""},
    ]:
        assert client.get("/connect/authorize", params={**params, **change}).status_code == 400


def test_disconnect_between_callback_and_completion_wins(flow):
    client, accounts, config, _ = flow
    info = profile(client, config)
    subject = "oauth2|freeagent|" + info["user_id"]
    accounts.disconnect(subject, 0)
    assert complete(client, config, info).status_code == 400
    assert accounts.store.get("account_links", key_for(subject))["active"] is False


def test_pending_records_do_not_hold_plaintext_provider_tokens(flow):
    client, accounts, config, _ = flow
    info = profile(client, config)
    assert "upstream-private" not in str(accounts.store.records)
    assert "upstream-refresh" not in str(accounts.store.records)
    assert complete(client, config, info).status_code == 200
    assert "upstream-private" not in str(accounts.store.records)


def test_bridge_restores_outer_management_session_cookie(flow):
    client, accounts, config, _ = flow
    login = client.get("/login")
    outer_cookie = client.cookies.get(COOKIE)
    outer_state = parse_qs(urlsplit(login.headers["location"]).query)["state"][0]
    assert accounts.store.get("web_state", key_for(outer_state))["session"] == outer_cookie
    state, _, _ = authorize(client, config)
    assert client.cookies.get(COOKIE) != outer_cookie
    result = client.get("/freeagent/callback", params={"state": state, "code": "x"})
    assert result.status_code == 307
    assert client.cookies.get(COOKIE) == outer_cookie
    assert accounts.store.get("web_state", key_for(outer_state))["session"] == client.cookies.get(COOKIE)


def test_readiness_exposes_only_protocol_version(flow):
    client, _, _, _ = flow
    assert client.get("/connect/ready").json() == {"protocol": "freeagent-sign-in-v1"}
