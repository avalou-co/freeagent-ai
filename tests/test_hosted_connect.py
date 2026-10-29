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


@pytest.fixture
def sandbox_flow(monkeypatch):
    accounts = Accounts(MemoryStore(), TokenCipher({"1": base64.b64encode(secrets.token_bytes(32)).decode()}, "1"))
    config = replace(
        settings(),
        connection_secret="synthetic-bridge-secret",
        sandbox_client_id="sandbox-client",
        sandbox_client_secret="synthetic-sandbox-secret",
        sandbox_company_ids=frozenset({"456"}),
    )
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append((method, url, kwargs))
        base = "https://api.sandbox.freeagent.com/v2/" if "sandbox" in url else "https://api.freeagent.com/v2/"
        if url.endswith("token_endpoint"):
            return {"access_token": "upstream-private", "refresh_token": "upstream-refresh", "expires_in": 3600}, {}
        if url.endswith("users/me"):
            return {"user": {"url": base + "users/123"}}, {}
        if url.endswith("company"):
            return {"company": {"url": base + "company", "id": "456"}}, {}
        pytest.fail("Unexpected upstream call")

    monkeypatch.setattr("freeagent_ai.hosted_connect.request_json", transport)
    with TestClient(create_app(config, accounts, verifier=object()), base_url=ORIGIN, follow_redirects=False) as client:
        yield client, accounts, config, calls


def start_environment(client, config, environment):
    if environment == "sandbox":
        login = client.get("/reviewer/login")
        assert login.status_code == 307
        assert urlsplit(login.headers["location"]).hostname == "example.auth0.com"
    verifier = "a" * 43
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    response = client.get(
        "/connect/authorize",
        params={
            "client_id": BRIDGE_CLIENT,
            "response_type": "code",
            "redirect_uri": config.issuer + "login/callback",
            "state": "auth0-transaction",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
    )
    assert response.status_code == 307
    location = urlsplit(response.headers["location"])
    query = parse_qs(location.query)
    assert query["client_id"] == ["sandbox-client" if environment == "sandbox" else config.freeagent_client_id]
    assert location.hostname == ("api.sandbox.freeagent.com" if environment == "sandbox" else "api.freeagent.com")
    return query["state"][0], verifier


@pytest.mark.parametrize("environment", ["production", "sandbox"])
def test_reviewer_login_environment_is_pinned_through_callback_and_completion(sandbox_flow, environment):
    client, accounts, config, calls = sandbox_flow
    state, verifier = start_environment(client, config, environment)
    # Callback input cannot override the environment selected in browser-bound state.
    response = client.get("/freeagent/callback", params={"state": state, "code": "x", "environment": "other"})
    assert response.status_code == 307
    code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]
    response = client.post(
        "/connect/token",
        headers=headers(config),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.issuer + "login/callback",
            "code_verifier": verifier,
        },
    )
    token = response.json()["access_token"]
    info = client.get("/connect/profile", headers={"Authorization": "Bearer " + token}).json()
    result = complete(client, config, info)
    assert result.status_code == 200
    subject = "oauth2|freeagent|" + info["user_id"]
    binding = accounts.bind(
        Principal(subject, frozenset(), result.json()["authenticated_at"], result.json()["generation"])
    )
    assert binding.environment == environment
    expected = config.upstream(environment)
    basic = (
        "Basic "
        + base64.b64encode(f"{expected.freeagent_client_id}:{expected.freeagent_client_secret}".encode()).decode()
    )
    assert calls[0][2]["headers"]["Authorization"] == basic
    assert all(("sandbox" in url) == (environment == "sandbox") for _, url, _ in calls)
    other = "production" if environment == "sandbox" else "sandbox"
    other_base = "https://api.freeagent.com/v2/" if other == "production" else "https://api.sandbox.freeagent.com/v2/"
    assert info["user_id"] != hashlib.sha256(f"{other}|456|{other_base}users/123".encode()).hexdigest()


def test_unlisted_sandbox_company_cannot_complete_login(sandbox_flow):
    client, accounts, config, _ = sandbox_flow
    state, _ = start_environment(client, config, "sandbox")
    object.__setattr__(config, "sandbox_company_ids", frozenset({"999"}))
    assert client.get("/freeagent/callback", params={"state": state, "code": "x"}).status_code == 400
    assert not any(collection == "account_links" for collection, _ in accounts.store.records)


def test_sandbox_configuration_is_all_or_nothing(monkeypatch):
    import json

    from freeagent_ai.hosted_auth import Settings

    values = {
        "GOOGLE_CLOUD_PROJECT": "example-project",
        "AUTH0_ISSUER": "https://example.auth0.com/",
        "AUTH0_MCP_CLIENT_ID": "mcp-client",
        "AUTH0_WEB_CLIENT_ID": "web-client",
        "AUTH0_WEB_CLIENT_SECRET": "synthetic-secret",
        "FREEAGENT_CLIENT_ID": "production-client",
        "FREEAGENT_CLIENT_SECRET": "synthetic-production-secret",
        "FREEAGENT_TOKEN_ENCRYPTION_KEY": json.dumps({"active": "1", "keys": {"1": "synthetic-key"}}),
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)
    for name in (
        "FREEAGENT_ENVIRONMENT",
        "FREEAGENT_REVIEWER_CLIENT_ID",
        "FREEAGENT_REVIEWER_CLIENT_SECRET",
        "FREEAGENT_REVIEWER_COMPANY_IDS",
    ):
        monkeypatch.delenv(name, raising=False)
    assert not Settings.from_env().reviewer_sandbox_enabled
    monkeypatch.setenv("FREEAGENT_REVIEWER_CLIENT_ID", "sandbox-client")
    with pytest.raises(ValueError, match="Reviewer sandbox"):
        Settings.from_env()
    monkeypatch.setenv("FREEAGENT_REVIEWER_CLIENT_SECRET", "synthetic-sandbox-secret")
    monkeypatch.setenv("FREEAGENT_REVIEWER_COMPANY_IDS", "456")
    config = Settings.from_env()
    assert config.upstream("production").freeagent_client_id == "production-client"
    assert config.upstream("sandbox").freeagent_client_id == "sandbox-client"
    for invalid in ("0", "*", "456, ", "https://attacker.invalid"):
        monkeypatch.setenv("FREEAGENT_REVIEWER_COMPANY_IDS", invalid)
        with pytest.raises(ValueError, match="Reviewer sandbox"):
            Settings.from_env()
    monkeypatch.setenv("FREEAGENT_REVIEWER_COMPANY_IDS", "456")
    monkeypatch.setenv("FREEAGENT_ENVIRONMENT", "sandbox")
    with pytest.raises(ValueError, match="Reviewer sandbox"):
        Settings.from_env()


def test_reviewer_marker_is_one_use_expiring_and_cannot_be_forged(sandbox_flow):
    from freeagent_ai.hosted_connect import FreeAgentConnect

    client, accounts, config, calls = sandbox_flow
    connect = FreeAgentConnect(config, accounts)
    client.get("/reviewer/login")
    marker = client.cookies.get(COOKIE)
    assert connect.browser_environment(marker) == "sandbox"
    assert connect.browser_environment(marker) == "production"
    assert connect.browser_environment("sandbox") == "production"
    client.get("/reviewer/login")
    marker = client.cookies.get(COOKIE)
    accounts.clock = lambda: time.time() + 601
    assert connect.browser_environment(marker) == "production"
    assert calls == []


def test_normal_login_does_not_inherit_reviewer_marker(sandbox_flow):
    client, accounts, config, _ = sandbox_flow
    client.get("/reviewer/login")
    client.get("/login")
    start_environment(client, config, "production")


def test_only_active_authenticated_sandbox_session_selects_sandbox(sandbox_flow):
    from freeagent_ai.hosted_connect import FreeAgentConnect

    _, accounts, config, _ = sandbox_flow
    connect = FreeAgentConnect(config, accounts)
    subject = "oauth2|freeagent|synthetic-reviewer"
    session = accounts.new_state("session", {"subject": subject})
    assert connect.browser_environment(session) == "production"
    record = accounts.replace(
        subject, "https://api.sandbox.freeagent.com/v2/company", "sandbox", {"access_token": "synthetic-token"}, 0
    )
    assert connect.browser_environment(session) == "sandbox"
    accounts.disconnect(subject, record["generation"])
    assert connect.browser_environment(session) == "production"


def test_reviewer_login_is_disabled_without_complete_configuration(flow):
    client, _, _, _ = flow
    assert client.get("/reviewer/login").status_code == 400


def test_sandbox_refresh_uses_sandbox_credentials_and_disabled_config_denies(sandbox_flow):
    from types import SimpleNamespace

    from freeagent_ai.hosted_client import HostedClient
    from freeagent_ai.hosted_deadline import Deadline

    _, accounts, config, _ = sandbox_flow
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append((url, kwargs))
        return {"access_token": "new-synthetic-token", "expires_in": 3600}, {}

    upstream = config.upstream("sandbox")
    client = HostedClient(
        accounts,
        SimpleNamespace(environment="sandbox"),
        Deadline(),
        upstream.freeagent_client_id,
        upstream.freeagent_client_secret,
        transport,
    )
    client.exchange({"refresh_token": "synthetic-refresh"})
    assert calls[0][0] == "https://api.sandbox.freeagent.com/v2/token_endpoint"
    assert (
        calls[0][1]["headers"]["Authorization"]
        == "Basic " + base64.b64encode(b"sandbox-client:synthetic-sandbox-secret").decode()
    )
    disabled = replace(config, sandbox_client_secret="")
    with pytest.raises(AccessDenied):
        disabled.upstream("sandbox")


def test_app_selects_refresh_client_from_binding_not_default_config(sandbox_flow, monkeypatch):
    from types import SimpleNamespace

    import freeagent_ai.hosted_app as hosted_app
    from freeagent_ai.hosted_deadline import Deadline

    _, accounts, config, _ = sandbox_flow
    factories = []
    original = hosted_app.Dispatcher

    def capture(*args, **kwargs):
        factories.append(kwargs["client_factory"])
        return original(*args, **kwargs)

    monkeypatch.setattr(hosted_app, "Dispatcher", capture)
    create_app(config, accounts, verifier=object())
    factory = factories[0]
    sandbox = factory(accounts, SimpleNamespace(environment="sandbox"), Deadline(), "ignored", "ignored")
    production = factory(accounts, SimpleNamespace(environment="production"), Deadline(), "ignored", "ignored")
    assert sandbox.client_id == "sandbox-client"
    assert sandbox.client_secret == "synthetic-sandbox-secret"
    assert sandbox.base == "https://api.sandbox.freeagent.com/v2/"
    assert production.client_id == config.freeagent_client_id
    assert production.base == "https://api.freeagent.com/v2/"
    object.__setattr__(config, "sandbox_client_secret", "")
    with pytest.raises(AccessDenied):
        factory(accounts, SimpleNamespace(environment="sandbox"), Deadline(), "ignored", "ignored")


def test_reviewer_web_login_hands_authenticated_session_to_chatgpt(sandbox_flow, monkeypatch):
    from types import SimpleNamespace

    from freeagent_ai.hosted_auth import GENERATION_CLAIM, PRIMARY_AUTH_CLAIM

    _, accounts, config, _ = sandbox_flow
    claims = {}
    verifier = SimpleNamespace(claims=lambda *args: claims)
    monkeypatch.setattr(
        "freeagent_ai.hosted_app.request_json", lambda *args, **kwargs: ({"id_token": "synthetic-id-token"}, {})
    )
    with TestClient(create_app(config, accounts, verifier=verifier), base_url=ORIGIN, follow_redirects=False) as client:
        login = client.get("/reviewer/login")
        outer = parse_qs(urlsplit(login.headers["location"]).query)
        marker = client.cookies.get(COOKIE)
        pkce = "a" * 43
        challenge = base64.urlsafe_b64encode(hashlib.sha256(pkce.encode()).digest()).decode().rstrip("=")
        response = client.get(
            "/connect/authorize",
            params={
                "client_id": BRIDGE_CLIENT,
                "response_type": "code",
                "redirect_uri": config.issuer + "login/callback",
                "state": "auth0-reviewer-login",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        assert urlsplit(response.headers["location"]).hostname == "api.sandbox.freeagent.com"
        state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        response = client.get("/freeagent/callback", params={"state": state, "code": "synthetic-code"})
        assert client.cookies.get(COOKIE) == marker
        code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]
        token = client.post(
            "/connect/token",
            headers=headers(config),
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": config.issuer + "login/callback",
                "code_verifier": pkce,
            },
        ).json()["access_token"]
        info = client.get("/connect/profile", headers={"Authorization": "Bearer " + token}).json()
        linked = complete(client, config, info)
        assert linked.status_code == 200
        claims.update(
            sub="oauth2|freeagent|" + info["user_id"],
            nonce=outer["nonce"][0],
            **{PRIMARY_AUTH_CLAIM: linked.json()["authenticated_at"], GENERATION_CLAIM: linked.json()["generation"]},
        )
        response = client.get("/auth/callback", params={"state": outer["state"][0], "code": "synthetic-auth0-code"})
        assert response.headers["location"] == "/account"
        assert client.cookies.get(COOKIE) != marker
        # A new ChatGPT transaction has no sandbox parameter or selector.
        response = client.get(
            "/connect/authorize",
            params={
                "client_id": BRIDGE_CLIENT,
                "response_type": "code",
                "redirect_uri": config.issuer + "login/callback",
                "state": "chatgpt-transaction",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        assert response.status_code == 307
        assert urlsplit(response.headers["location"]).hostname == "api.sandbox.freeagent.com"


def test_pending_browser_cookie_is_not_authenticated_until_confidential_complete(flow):
    client, accounts, config, _ = flow
    info = profile(client, config)
    cookie = client.cookies.get(COOKIE)
    pending = accounts.store.get("web_state", key_for(cookie))
    assert pending["kind"] == "pending_document_session"
    # Canonical state retains only a hash reference, never the browser cookie.
    assert all(cookie not in str(row) for row in accounts.store.records.values())
    denied = client.post("/documents/download", data={"grant": "a" * 43}, headers={"Origin": ORIGIN})
    assert denied.status_code == 400
    assert "Sign in" in denied.text
    assert complete(client, config, info, "oauth2|freeagent|wrong").status_code == 400
    assert accounts.store.get("web_state", key_for(cookie))["kind"] == "pending_document_session"
    result = complete(client, config, info)
    assert result.status_code == 200
    session = accounts.store.get("web_state", key_for(cookie))
    assert session["kind"] == "session"
    assert session["connection_generation"] == result.json()["generation"]
    assert session["subject"] == "oauth2|freeagent|" + info["user_id"]
    assert complete(client, config, info).status_code == 400
    assert accounts.store.get("web_state", key_for(cookie)) == session


@pytest.mark.parametrize(
    "change", [{"subject": "other"}, {"company": "other"}, {"environment": "sandbox"}, {"expires": 0}]
)
def test_tampered_or_expired_pending_browser_record_is_never_activated(flow, change):
    client, accounts, config, _ = flow
    info = profile(client, config)
    cookie = client.cookies.get(COOKIE)
    accounts.store.mutate("web_state", key_for(cookie), lambda old: {**old, **change})
    assert complete(client, config, info).status_code == 400
    assert accounts.store.get("web_state", key_for(cookie))["kind"] != "session"
    assert complete(client, config, info).status_code == 400


def test_normal_chatgpt_login_replaces_old_or_arbitrary_cookie_without_fixation(flow):
    client, accounts, config, _ = flow
    client.cookies.set(COOKIE, "untrusted-prior-cookie", domain="freeagent-ai.avalou.co")
    first = profile(client, config)
    first_cookie = client.cookies.get(COOKIE)
    assert first_cookie != "untrusted-prior-cookie"
    assert not accounts.store.get("web_state", key_for("untrusted-prior-cookie"))
    assert complete(client, config, first).status_code == 200
    old = accounts.store.get("web_state", key_for(first_cookie))
    second = profile(client, config)
    second_cookie = client.cookies.get(COOKIE)
    assert second_cookie != first_cookie
    assert accounts.store.get("web_state", key_for(second_cookie))["kind"] == "pending_document_session"
    result = complete(client, config, second)
    assert result.status_code == 200
    assert accounts.store.get("web_state", key_for(first_cookie)) == old
    assert (
        accounts.store.get("web_state", key_for(second_cookie))["connection_generation"]
        == old["connection_generation"] + 1
    )


def test_stale_concurrent_completion_cannot_activate_or_overwrite_newer_generation(flow):
    client, accounts, config, _ = flow
    first = profile(client, config)
    first_cookie = client.cookies.get(COOKIE)
    second = profile(client, config)
    second_cookie = client.cookies.get(COOKIE)
    result = complete(client, config, first)
    assert result.status_code == 200
    active = accounts.store.get("web_state", key_for(first_cookie))
    assert complete(client, config, second).status_code == 400
    assert accounts.store.get("web_state", key_for(second_cookie))["kind"] == "pending_document_session"
    assert accounts.store.get("web_state", key_for(first_cookie)) == active
    linked = accounts.store.get("account_links", key_for(active["subject"]))
    assert linked["generation"] == active["connection_generation"]


def test_normal_management_login_restores_only_server_recognized_outer_marker(flow):
    client, accounts, config, _ = flow
    client.get("/login")
    marker = client.cookies.get(COOKIE)
    assert accounts.store.get("web_state", key_for(marker))["kind"] == "login_browser"
    info = profile(client, config)
    assert client.cookies.get(COOKIE) == marker
    assert complete(client, config, info).status_code == 200
    # Only the subsequent signed /auth/callback can create the management session.
    assert accounts.store.get("web_state", key_for(marker))["kind"] == "login_browser"
