"""Shared FreeAgent OAuth mechanics, independent of browser/session policy."""

import base64
import re
import time

from .hosted_accounts import AccessDenied


def freeagent_base(environment):
    if environment not in {"production", "sandbox"}:
        raise ValueError("Unknown FreeAgent environment")
    return "https://api.freeagent.com/v2/" if environment == "production" else "https://api.sandbox.freeagent.com/v2/"


def exchange_identity(settings, code, redirect_uri, deadline, transport, *, environment=None):
    """Exchange once and verify the provider's user/company before returning credentials."""
    base = freeagent_base(environment or settings.environment)
    basic = base64.b64encode(f"{settings.freeagent_client_id}:{settings.freeagent_client_secret}".encode()).decode()
    tokens, _ = transport(
        "POST",
        base + "token_endpoint",
        deadline,
        form={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
        headers={"Authorization": "Basic " + basic},
    )
    headers = {"Authorization": "Bearer " + tokens["access_token"]}
    user, _ = transport("GET", base + "users/me", deadline, headers=headers)
    company, _ = transport("GET", base + "company", deadline, headers=headers)
    user_url = user.get("user", {}).get("url", "")
    company = company.get("company", {})
    if (
        not re.fullmatch(re.escape(base) + r"users/[0-9]+", user_url)
        or company.get("url") != base + "company"
        or not re.fullmatch(r"[1-9][0-9]*", str(company.get("id", "")))
    ):
        raise AccessDenied("Could not verify FreeAgent user and company")
    credentials = {key: tokens[key] for key in ("access_token", "refresh_token")}
    credentials.update(expires_at=time.time() + int(tokens["expires_in"]), user=user_url)
    return credentials, company
