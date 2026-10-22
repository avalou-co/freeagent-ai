"""Auth0 JWT verification and fail-closed hosted configuration."""

import json
import math
import os
import re
import time
from dataclasses import dataclass, replace

import jwt

from .hosted_accounts import AccessDenied, Principal
from .hosted_deadline import Deadline, deadline_context

ORIGIN = "https://freeagent-ai.avalou.co"
PRIMARY_AUTH_CLAIM = ORIGIN + "/primary_auth_time"
GENERATION_CLAIM = ORIGIN + "/connection_generation"
MAX_SESSION_SECONDS = 30 * 24 * 60 * 60


@dataclass(frozen=True)
class Settings:
    issuer: str
    mcp_client_id: str
    web_client_id: str
    web_client_secret: str
    freeagent_client_id: str
    freeagent_client_secret: str
    encryption_keys: dict[str, str]
    active_key: str
    project: str = ""
    environment: str = "production"
    file_hosts: frozenset[str] = frozenset()
    challenge: str = ""
    connection_secret: str = ""
    connection_name: str = "freeagent"

    sandbox_client_id: str = ""
    sandbox_client_secret: str = ""
    sandbox_company_ids: frozenset[str] = frozenset()

    @property
    def reviewer_sandbox_enabled(self):
        return bool(self.sandbox_client_id and self.sandbox_client_secret and self.sandbox_company_ids)

    def upstream(self, environment):
        if environment == self.environment:
            return self
        if environment == "sandbox" and self.reviewer_sandbox_enabled:
            return replace(
                self,
                environment="sandbox",
                freeagent_client_id=self.sandbox_client_id,
                freeagent_client_secret=self.sandbox_client_secret,
            )
        raise AccessDenied("FreeAgent environment is not configured")

    @classmethod
    def from_env(cls):
        required = [
            "GOOGLE_CLOUD_PROJECT",
            "AUTH0_ISSUER",
            "AUTH0_MCP_CLIENT_ID",
            "AUTH0_WEB_CLIENT_ID",
            "AUTH0_WEB_CLIENT_SECRET",
            "FREEAGENT_CLIENT_ID",
            "FREEAGENT_CLIENT_SECRET",
            "FREEAGENT_TOKEN_ENCRYPTION_KEY",
        ]
        if any(not os.environ.get(key) for key in required):
            raise ValueError("Hosted configuration incomplete; see docs/hosted.md (no local credential fallback)")
        issuer = os.environ["AUTH0_ISSUER"]
        if not re.fullmatch(r"https://[a-z0-9.-]+\.auth0\.com/", issuer):
            raise ValueError("AUTH0_ISSUER must be the HTTPS Auth0 tenant origin with trailing slash")
        keys = json.loads(os.environ["FREEAGENT_TOKEN_ENCRYPTION_KEY"])
        environment = os.environ.get("FREEAGENT_ENVIRONMENT", "production")
        if environment not in {"production", "sandbox"}:
            raise ValueError("FREEAGENT_ENVIRONMENT must be production or sandbox")
        sandbox_id = os.environ.get("FREEAGENT_REVIEWER_CLIENT_ID", "")
        sandbox_secret = os.environ.get("FREEAGENT_REVIEWER_CLIENT_SECRET", "")
        sandbox_companies = frozenset(filter(None, os.environ.get("FREEAGENT_REVIEWER_COMPANY_IDS", "").split(",")))
        if any((sandbox_id, sandbox_secret, sandbox_companies)) and (
            environment != "production"
            or not all((sandbox_id, sandbox_secret, sandbox_companies))
            or any(not re.fullmatch(r"[1-9][0-9]*", value) for value in sandbox_companies)
        ):
            raise ValueError("Reviewer sandbox requires separate credentials and explicit company IDs in production")
        hosts = frozenset(filter(None, os.environ.get("OPENAI_FILE_DOWNLOAD_HOSTS", "").split(",")))
        if any(not re.fullmatch(r"[a-z0-9.-]+", host) for host in hosts):
            raise ValueError("File origins must be exact DNS hostnames, no wildcards")
        return cls(
            issuer,
            os.environ["AUTH0_MCP_CLIENT_ID"],
            os.environ["AUTH0_WEB_CLIENT_ID"],
            os.environ["AUTH0_WEB_CLIENT_SECRET"],
            os.environ["FREEAGENT_CLIENT_ID"],
            os.environ["FREEAGENT_CLIENT_SECRET"],
            keys["keys"],
            keys["active"],
            project=os.environ["GOOGLE_CLOUD_PROJECT"],
            environment=environment,
            file_hosts=hosts,
            challenge=os.environ.get("OPENAI_DOMAIN_CHALLENGE", ""),
            sandbox_client_id=sandbox_id,
            sandbox_client_secret=sandbox_secret,
            sandbox_company_ids=sandbox_companies,
            connection_secret=os.environ.get("AUTH0_FREEAGENT_CONNECTION_SECRET", ""),
        )


class Verifier:
    def __init__(self, settings, key_client=None):
        self.settings = settings

        class BoundedJWKS(jwt.PyJWKClient):
            def fetch_data(self):
                from .hosted_client import request_json

                try:
                    deadline = deadline_context.get()
                except LookupError:
                    deadline = Deadline(5)
                data, _ = request_json("GET", settings.issuer + ".well-known/jwks.json", deadline)
                if self.jwk_set_cache is not None:
                    self.jwk_set_cache.put(data)
                return data

        self.keys = key_client or BoundedJWKS(settings.issuer + ".well-known/jwks.json", timeout=5)

    def claims(self, token, audience):
        try:
            key = self.keys.get_signing_key_from_jwt(token).key
            data = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.settings.issuer,
                audience=audience,
                options={"require": ["iss", "aud", "sub", "iat", "exp", PRIMARY_AUTH_CLAIM]},
            )
            auth = data[PRIMARY_AUTH_CLAIM]
            if (
                isinstance(auth, bool)
                or not isinstance(auth, (int, float))
                or not math.isfinite(auth)
                or auth <= 0
                or auth > data["iat"] + 1
                or data["exp"] - data["iat"] > 3600
                or not isinstance(data["sub"], str)
                or not data["sub"]
            ):
                raise ValueError()
            return data
        except Exception:
            raise AccessDenied("Invalid or expired authorization; sign in again") from None

    def principal(self, token):
        data = self.claims(token, ORIGIN + "/mcp")
        # A refreshed access token must not extend the original authorization window.
        if time.time() >= data[PRIMARY_AUTH_CLAIM] + MAX_SESSION_SECONDS:
            raise AccessDenied("ChatGPT session expired; sign in again")
        if data.get("azp") != self.settings.mcp_client_id:
            raise AccessDenied("OAuth client is not authorized for this plugin")
        generation = data.get(GENERATION_CLAIM)
        federated = data["sub"].startswith(f"oauth2|{self.settings.connection_name}|")
        if federated and (type(generation) is not int or generation < 1):
            raise AccessDenied("FreeAgent connection authorization is missing")
        if generation is not None and not federated:
            raise AccessDenied("Invalid FreeAgent connection identity")
        return Principal(data["sub"], frozenset(data.get("scope", "").split()), data[PRIMARY_AUTH_CLAIM], generation)
