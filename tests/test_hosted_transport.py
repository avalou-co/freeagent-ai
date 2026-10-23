"""Proxy-host compatibility must not disable MCP host/origin protections."""

from dataclasses import replace
from types import SimpleNamespace

import pytest
from conftest import settings
from starlette.testclient import TestClient

from freeagent_ai.hosted_accounts import Principal
from freeagent_ai.hosted_app import create_app
from freeagent_ai.hosted_auth import ORIGIN
from freeagent_ai.public_tools import REGISTRY

BACKEND = "service-synthetic.europe-west2.run.app"


@pytest.mark.parametrize("host", ["freeagent-ai.avalou.co", BACKEND])
def test_authorized_tool_discovery_accepts_exact_public_and_configured_proxy_host(accounts, host):
    principal = Principal("synthetic-reviewer", frozenset({"freeagent:read"}), 100)
    verifier = SimpleNamespace(principal=lambda _: principal)
    config = replace(settings(), backend_host=BACKEND)
    with TestClient(create_app(config, accounts, verifier), base_url=ORIGIN) as client:
        result = client.post(
            "/mcp",
            headers={
                "Host": host,
                "Authorization": "Bearer synthetic",
                "Accept": "application/json, text/event-stream",
            },
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        )
        assert result.status_code == 200
        assert len(result.json()["result"]["tools"]) == len(REGISTRY)


@pytest.mark.parametrize(
    "configured,host,origin,status",
    [
        (False, BACKEND, None, 421),
        (True, "attacker.invalid", None, 421),
        (True, BACKEND + ".attacker.invalid", None, 421),
        (True, BACKEND, "https://attacker.invalid", 403),
    ],
)
def test_unlisted_hosts_and_origins_remain_rejected(accounts, configured, host, origin, status):
    verifier = SimpleNamespace(principal=lambda _: Principal("synthetic", frozenset(), 100))
    config = replace(settings(), backend_host=BACKEND if configured else "")
    with TestClient(create_app(config, accounts, verifier), base_url=ORIGIN) as client:
        headers = {
            "Host": host,
            "Authorization": "Bearer synthetic",
            "X-Forwarded-Host": "freeagent-ai.avalou.co",
            "Accept": "application/json, text/event-stream",
        }
        if origin:
            headers["Origin"] = origin
        result = client.post("/mcp", headers=headers, json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        assert result.status_code == status


def test_proxy_host_does_not_bypass_oauth(accounts):
    with TestClient(
        create_app(replace(settings(), backend_host=BACKEND), accounts, verifier=object()), base_url=ORIGIN
    ) as client:
        result = client.post("/mcp", headers={"Host": BACKEND}, json={})
        assert result.status_code == 401
        assert "oauth-protected-resource/mcp" in result.headers["WWW-Authenticate"]
