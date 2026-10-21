"""Synthetic hosted-account fixtures shared across test modules."""

import base64
import secrets
from contextlib import contextmanager

import pytest

from freeagent_ai.hosted_accounts import Accounts, MemoryStore, TokenCipher
from freeagent_ai.hosted_auth import Settings
from freeagent_ai.hosted_client import principal_context
from freeagent_ai.hosted_deadline import Deadline, deadline_context


@pytest.fixture
def accounts():
    cipher = TokenCipher({"1": base64.b64encode(secrets.token_bytes(32)).decode()}, "1")
    return Accounts(MemoryStore(), cipher, clock=lambda: 100)


def settings():
    return Settings(
        "https://example.auth0.com/",
        "mcp-client",
        "web-client",
        "test-only-web-secret",
        "fa-client",
        "test-only-fa-secret",
        {},
        "1",
    )


@pytest.fixture
def hosted_context():
    @contextmanager
    def enter(principal):
        p, d = principal_context.set(principal), deadline_context.set(Deadline())
        try:
            yield
        finally:
            principal_context.reset(p)
            deadline_context.reset(d)

    return enter
