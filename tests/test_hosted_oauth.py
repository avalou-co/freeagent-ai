"""Both account-linking routes use verified provider identities before saving tokens."""

import time
from dataclasses import replace

import pytest
from conftest import settings
from starlette.testclient import TestClient

from freeagent_ai.hosted_accounts import Principal, key_for
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN
from freeagent_ai.hosted_oauth import freeagent_base


@pytest.mark.parametrize("environment", ["production", "sandbox"])
@pytest.mark.parametrize("invalid", [None, "user", "company_url", "company_id"])
def test_management_callback_verifies_provider_identity_before_account_replacement(
    accounts, monkeypatch, environment, invalid
):
    accounts.clock = time.time
    base = freeagent_base(environment)
    calls = []

    def transport(method, url, deadline, **kwargs):
        calls.append((method, url))
        if url.endswith("token_endpoint"):
            return {"access_token": "synthetic-access", "refresh_token": "synthetic-refresh", "expires_in": 3600}, {}
        if url.endswith("users/me"):
            return {"user": {"url": "https://attacker.invalid/users/1" if invalid == "user" else base + "users/1"}}, {}
        return {
            "company": {
                "url": base + "company/other" if invalid == "company_url" else base + "company",
                "id": 0 if invalid == "company_id" else 123,
            }
        }, {}

    monkeypatch.setattr("freeagent_ai.hosted_app.request_json", transport)
    subject = "auth0|synthetic-management"
    session = accounts.new_state("session", {"subject": subject})
    pending = accounts.new_state(
        "freeagent",
        {
            "subject": subject,
            "session": session,
            "generation": 0,
            "environment": environment,
        },
    )
    app = create_app(replace(settings(), environment=environment), accounts, verifier=object())
    with TestClient(app, base_url=ORIGIN) as client:
        client.cookies.set("__session", session, domain="freeagent-ai.avalou.co", path="/")
        response = client.get("/freeagent/callback", params={"state": pending, "code": "synthetic-code"})
    assert len(calls) == 3
    if invalid:
        assert response.status_code == 400
        assert not accounts.store.get("account_links", key_for(subject))
    else:
        assert response.status_code == 200
        binding = accounts.bind(Principal(subject, frozenset(), time.time() + 1))
        assert binding.environment == environment
        assert binding.company == base + "company"
        assert accounts.credentials(binding)["user"] == base + "users/1"
    assert "synthetic-access" not in str(accounts.store.records)
