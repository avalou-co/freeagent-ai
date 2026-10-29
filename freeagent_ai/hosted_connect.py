"""Confidential OAuth bridge: FreeAgent sign-in -> Auth0 -> ChatGPT.

Only the dedicated Auth0 custom connection can redeem codes or complete a login.
Upstream credentials are encrypted in short-lived records, never profile claims.
"""

import base64
import hashlib
import hmac
import re
import secrets
from urllib.parse import urlencode

import anyio
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from .hosted_accounts import AccessDenied, key_for
from .hosted_auth import ORIGIN
from .hosted_client import request_json
from .hosted_deadline import Deadline
from .hosted_oauth import exchange_identity, freeagent_base

BRIDGE_CLIENT = "freeagent-ai-auth0"
COOKIE = "__session"  # Firebase Hosting forwards only this cookie to Cloud Run.


class FreeAgentConnect:
    def __init__(self, settings, accounts):
        self.settings, self.accounts = settings, accounts

    def enabled(self):
        if not self.settings.connection_secret:
            raise AccessDenied("FreeAgent sign-in is not configured")

    def authenticate(self, request, form=None):
        self.enabled()
        expected = "Basic " + base64.b64encode(f"{BRIDGE_CLIENT}:{self.settings.connection_secret}".encode()).decode()
        header = request.headers.get("authorization", "")
        # Auth0's generic OAuth2 connector may use client_secret_post. Never
        # accept ambiguous credentials or fall back from a failed header.
        if (
            not header
            and form is not None
            and form.get("client_id") == BRIDGE_CLIENT
            and hmac.compare_digest(str(form.get("client_secret", "")), self.settings.connection_secret)
        ):
            return
        if not hmac.compare_digest(header, expected):
            raise AccessDenied("Invalid connection client")

    def peek(self, token, kind):
        value = self.accounts.store.get("web_state", key_for(token)) if token else {}
        if value.get("kind") != kind or value.get("used") or value.get("expires", 0) <= self.accounts.clock():
            raise AccessDenied("Connection expired; connect again from ChatGPT")
        return value

    async def authorize(self, request):
        self.enabled()
        q = request.query_params
        callback = self.settings.issuer + "login/callback"
        if (
            q.get("client_id") != BRIDGE_CLIENT
            or q.get("response_type") != "code"
            or q.get("redirect_uri") != callback
            or not q.get("state")
            or len(q["state"]) > 2048
            or q.get("code_challenge_method") != "S256"
            or not re.fullmatch(r"[A-Za-z0-9_-]{43}", q.get("code_challenge", ""))
        ):
            raise AccessDenied("Invalid connection authorization request")
        prior_session = request.cookies.get(COOKIE, "")
        prior_record = (
            await anyio.to_thread.run_sync(self.accounts.store.get, "web_state", key_for(prior_session))
            if prior_session
            else {}
        )
        management_session = (
            prior_record.get("kind") in {"login_browser", "reviewer_entry"}
            and not prior_record.get("used")
            and prior_record.get("expires", 0) > self.accounts.clock()
        )
        environment = await anyio.to_thread.run_sync(self.browser_environment, prior_session)
        config = self.settings.upstream(environment)
        browser = secrets.token_urlsafe(32)
        state = await anyio.to_thread.run_sync(
            lambda: self.accounts.new_state(
                "connect_browser",
                {
                    "browser": browser,
                    "environment": environment,
                    "state": q["state"],
                    "challenge": q["code_challenge"],
                    "prior_session": prior_session if management_session else "",
                    "management_session": management_session,
                },
            )
        )
        response = self.upstream_redirect(state, config)
        response.set_cookie(COOKIE, browser, secure=True, httponly=True, samesite="lax", path="/", max_age=600)
        return response

    def upstream_redirect(self, state, config):
        return RedirectResponse(
            freeagent_base(config.environment)
            + "approve_app?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": config.freeagent_client_id,
                    "redirect_uri": ORIGIN + "/freeagent/callback",
                    "state": state,
                }
            ),
            status_code=307,
        )

    def browser_environment(self, cookie):
        """Only an expiring server-owned reviewer login/session selects sandbox."""
        if not self.settings.reviewer_sandbox_enabled or not cookie:
            return self.settings.environment
        record = self.accounts.store.get("web_state", key_for(cookie))
        if record.get("used") or record.get("expires", 0) <= self.accounts.clock():
            return self.settings.environment
        if record.get("kind") == "reviewer_entry":
            self.accounts.take_state(cookie, "reviewer_entry")
            return "sandbox"
        if record.get("kind") == "session":
            link = self.accounts.store.get("account_links", key_for(record.get("subject", "")))
            if link.get("active") and link.get("environment") == "sandbox":
                return "sandbox"
        return self.settings.environment

    def is_callback(self, request):
        token = request.query_params.get("state", "")
        return self.accounts.store.get("web_state", key_for(token)).get("kind") == "connect_browser"

    async def callback(self, request):
        state_token = request.query_params.get("state", "")
        pending = await anyio.to_thread.run_sync(self.peek, state_token, "connect_browser")
        if not hmac.compare_digest(pending["browser"], request.cookies.get(COOKIE, "")):
            raise AccessDenied("Connection browser mismatch; start again from ChatGPT")
        state = await anyio.to_thread.run_sync(self.accounts.take_state, state_token, "connect_browser")
        callback = self.settings.issuer + "login/callback"
        browser_session = ""
        if request.query_params.get("error") or not request.query_params.get("code"):
            response = RedirectResponse(callback + "?" + urlencode({"error": "access_denied", "state": state["state"]}))
        else:

            def exchange():
                config = self.settings.upstream(state["environment"])
                credentials, company = exchange_identity(
                    config,
                    request.query_params["code"],
                    ORIGIN + "/freeagent/callback",
                    Deadline(),
                    request_json,
                )
                if (
                    config.environment == "sandbox"
                    and self.settings.reviewer_sandbox_enabled
                    and str(company["id"]) not in self.settings.sandbox_company_ids
                ):
                    raise AccessDenied("This sandbox company is not configured for review")
                user_url, company_url = credentials["user"], company["url"]
                # Identity is company + user + environment, never an email address.
                identity = hashlib.sha256(f"{config.environment}|{company['id']}|{user_url}".encode()).hexdigest()
                subject = f"oauth2|{self.settings.connection_name}|{identity}"
                current = self.accounts.store.get("account_links", key_for(subject))
                authenticated_at = int(self.accounts.clock())
                browser_session = ""
                if not state.get("management_session"):
                    browser_session = self.accounts.new_state(
                        "pending_document_session",
                        {
                            "subject": subject,
                            "company": company_url,
                            "environment": config.environment,
                            "primary_auth_time": authenticated_at,
                        },
                        ttl=3600,
                    )
                code = self.accounts.new_state(
                    "connect_code",
                    {
                        "identity": identity,
                        "environment": config.environment,
                        "subject": subject,
                        "company": company_url,
                        "generation": current.get("generation", 0),
                        "challenge": state["challenge"],
                        "tokens": self.accounts.cipher.seal(credentials, subject),
                        "authenticated_at": authenticated_at,
                        "browser_session_key": key_for(browser_session) if browser_session else "",
                    },
                    ttl=120,
                )
                return code, browser_session

            code, browser_session = await anyio.to_thread.run_sync(exchange)
            response = RedirectResponse(callback + "?" + urlencode({"code": code, "state": state["state"]}))
        # Restore only a server-recognized outer management transaction. A normal
        # ChatGPT login must replace an old account session with this newly verified
        # browser's pending session; it cannot inherit an arbitrary prior cookie.
        if state.get("management_session") and state.get("prior_session"):
            response.set_cookie(
                COOKIE, state["prior_session"], secure=True, httponly=True, samesite="lax", path="/", max_age=600
            )
        elif browser_session:
            response.set_cookie(
                COOKIE, browser_session, secure=True, httponly=True, samesite="lax", path="/", max_age=3600
            )
        else:
            response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="lax")
        return response

    async def token(self, request):
        form = await request.form(max_fields=7, max_files=0)
        self.authenticate(request, form)
        code = str(form.get("code", ""))
        record = await anyio.to_thread.run_sync(self.peek, code, "connect_code")
        verifier = str(form.get("code_verifier", ""))
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        if (
            form.get("grant_type") != "authorization_code"
            or form.get("redirect_uri") != self.settings.issuer + "login/callback"
            or not re.fullmatch(r"[A-Za-z0-9._~-]{43,128}", verifier)
            or not hmac.compare_digest(record["challenge"], challenge)
        ):
            raise AccessDenied("Invalid connection code exchange")
        record = await anyio.to_thread.run_sync(self.accounts.take_state, code, "connect_code")
        token = await anyio.to_thread.run_sync(lambda: self.accounts.new_state("connect_profile", record, ttl=120))
        return JSONResponse({"access_token": token, "token_type": "Bearer", "expires_in": 120})

    async def profile(self, request):
        self.enabled()
        header = request.headers.get("authorization", "")
        if not header.startswith("Bearer "):
            raise AccessDenied("Connection profile requires a bearer token")
        record = await anyio.to_thread.run_sync(self.accounts.take_state, header[7:], "connect_profile")
        receipt = await anyio.to_thread.run_sync(lambda: self.accounts.new_state("connect_receipt", record, ttl=120))
        return JSONResponse({"user_id": record["identity"], "app_metadata": {"freeagent_login_receipt": receipt}})

    async def complete(self, request):
        self.authenticate(request)
        form = await request.form(max_fields=2, max_files=0)
        receipt = str(form.get("receipt", ""))
        record = await anyio.to_thread.run_sync(self.peek, receipt, "connect_receipt")
        if form.get("subject") != record["subject"]:
            raise AccessDenied("Connection identity mismatch")
        record = await anyio.to_thread.run_sync(self.accounts.take_state, receipt, "connect_receipt")

        def commit():
            self.settings.upstream(record["environment"])
            linked = self.accounts.replace(
                record["subject"],
                record["company"],
                record["environment"],
                self.accounts.cipher.open(record["tokens"], record["subject"]),
                record["generation"],
            )
            if record.get("browser_session_key"):

                def activate(old):
                    if (
                        old.get("kind") != "pending_document_session"
                        or old.get("expires", 0) <= self.accounts.clock()
                        or old.get("subject") != record["subject"]
                        or old.get("company") != record["company"]
                        or old.get("environment") != record["environment"]
                        or old.get("primary_auth_time") != record["authenticated_at"]
                    ):
                        raise AccessDenied("Browser authorization expired; reconnect from ChatGPT")
                    return {**old, "kind": "session", "connection_generation": linked["generation"]}

                self.accounts.store.mutate("web_state", record["browser_session_key"], activate)
            return linked

        linked = await anyio.to_thread.run_sync(commit)
        return JSONResponse({"generation": linked["generation"], "authenticated_at": record["authenticated_at"]})

    async def ready(self, request):
        self.enabled()
        return JSONResponse({"protocol": "freeagent-sign-in-v1"})

    def routes(self):
        return [
            Route("/connect/ready", self.ready),
            Route("/connect/authorize", self.authorize),
            Route("/connect/token", self.token, methods=["POST"]),
            Route("/connect/profile", self.profile),
            Route("/connect/complete", self.complete, methods=["POST"]),
        ]
