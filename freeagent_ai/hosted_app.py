"""Cloud Run entrypoint: OAuth-protected MCP and a small account linking site."""

import base64
import hashlib
import html
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from urllib.parse import urlencode

import anyio
from mcp.server.lowlevel.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from .hosted_accounts import AccessDenied, Accounts, FirestoreStore, TokenCipher, key_for
from .hosted_auth import ORIGIN, PRIMARY_AUTH_CLAIM, Settings, Verifier
from .hosted_client import principal_context, request_json
from .hosted_connect import FreeAgentConnect
from .hosted_deadline import Deadline, deadline_context
from .hosted_oauth import exchange_identity, freeagent_base
from .landing import ROOT as LANDING_ROOT
from .landing import SITE_NOTICES
from .landing import render as render_landing
from .landing import validate_config as validate_landing_config
from .public_tools import REGISTRY, Dispatcher, PublicToolsResult


def page(title, body):
    return HTMLResponse(
        f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{html.escape(title)}</title><body><main><h1>{html.escape(title)}</h1>{body}</main></body></html>'
    )


class SecurityHeaders:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def headers(message):
            if message["type"] == "http.response.start":
                marketing = scope.get("path") == "/" or scope.get("path", "").startswith("/landing-assets/")
                csp = "default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'"
                if marketing:
                    csp += "; style-src 'self'; script-src 'self'; font-src 'self'; img-src 'self'"
                message.setdefault("headers", []).extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"referrer-policy", b"no-referrer"),
                        (
                            b"content-security-policy",
                            csp.encode(),
                        ),
                    ]
                )
            await send(message)

        await self.app(scope, receive, headers)


class ScopeMirror:
    """Preserve OpenAI's top-level extension through the SDK's core Tool serializer.

    MCP 2 serializes only core Tool fields. The trusted scope declaration survives
    under _meta; mirror it onto tools/list's JSON wire response without modifying
    inputs or financial results. The hosted transport is JSON, never SSE.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        start, parts = None, []

        async def mirror(message):
            nonlocal start
            if message["type"] == "http.response.start":
                content_type = dict(message.get("headers", [])).get(b"content-type", b"")
                if scope.get("path") == "/mcp" and content_type.startswith(b"application/json"):
                    start = message
                    return
            if start is not None and message["type"] == "http.response.body":
                parts.append(message.get("body", b""))
                if message.get("more_body", False):
                    return
                data = b"".join(parts)
                try:
                    payload = json.loads(data)
                    result = payload.get("result") if isinstance(payload, dict) else None
                    if isinstance(result, dict) and isinstance(result.get("tools"), list):
                        for descriptor in result["tools"]:
                            schemes = descriptor.get("_meta", {}).get("securitySchemes")
                            if schemes is not None:
                                descriptor["securitySchemes"] = schemes
                        data = json.dumps(payload).encode()
                except ValueError:
                    pass
                start["headers"] = [
                    (key, value) for key, value in start.get("headers", []) if key.lower() != b"content-length"
                ]
                start["headers"].append((b"content-length", str(len(data)).encode()))
                await send(start)
                start = None
                await send({**message, "body": data})
                return
            await send(message)

        await self.app(scope, receive, mirror)


class MCPAuth:
    def __init__(self, manager, verifier):
        self.manager, self.verifier = manager, verifier

    async def __call__(self, scope, receive, send):
        raw = dict(scope.get("headers", [])).get(b"authorization", b"")
        try:
            scheme, value = raw.decode("ascii").split(" ", 1)
            if scheme.lower() != "bearer" or len(value) > 16384:
                raise AccessDenied("Authorization required")
            deadline = Deadline()
            principal = await anyio.to_thread.run_sync(self.verifier.principal, value)
        except (ValueError, AccessDenied, UnicodeError):
            response = PlainTextResponse(
                "Sign in to connect FreeAgent",
                status_code=401,
                headers={
                    "WWW-Authenticate": f'Bearer resource_metadata="{ORIGIN}/.well-known/oauth-protected-resource/mcp"'
                },
            )
            await response(scope, receive, send)
            return
        p, d = principal_context.set(principal), deadline_context.set(deadline)
        try:
            await self.manager.handle_request(scope, receive, send)
        finally:
            principal_context.reset(p)
            deadline_context.reset(d)


def create_app(settings=None, accounts=None, verifier=None, dispatcher=None):
    # An absent configuration leaves the existing service in its pre-launch state.
    # A partial/malformed launch configuration fails startup rather than exposing
    # a public page with guessed directory links or unapproved policies.
    launch = os.environ.get("FREEAGENT_LANDING_CONFIG")
    landing_config = validate_landing_config(json.loads(launch)) if launch else None
    landing_html = render_landing(landing_config) if landing_config else None
    settings = settings or Settings.from_env()
    accounts = accounts or Accounts(
        FirestoreStore(settings.project), TokenCipher(settings.encryption_keys, settings.active_key)
    )
    connect = FreeAgentConnect(settings, accounts)
    verifier = verifier or Verifier(settings)
    dispatcher = dispatcher or Dispatcher(
        accounts, settings.freeagent_client_id, settings.freeagent_client_secret, settings.file_hosts
    )

    async def tools(context, params):
        return PublicToolsResult(tools=[operation.descriptor for operation in REGISTRY.values()])

    async def invoke(context, params):
        return await anyio.to_thread.run_sync(dispatcher.call_tool, params.name, params.arguments or {})

    server = Server(
        "freeagent-ai",
        version="0.3.0",
        on_list_tools=tools,
        on_call_tool=invoke,
        get_tool_input_schema=lambda name: REGISTRY[name].descriptor.input_schema if name in REGISTRY else None,
        instructions="Use the packaged FreeAgent workflows. Ask for business inputs; never guess. Show each write plan and obtain approval, then verify readback. Correct only entries created in this user request. Connect or reconnect through ChatGPT to authorize your FreeAgent account. ChatGPT stays connected for up to 30 days with automatic token renewal.",
    )
    manager = StreamableHTTPSessionManager(
        server,
        json_response=True,
        stateless=True,
        security_settings=TransportSecuritySettings(allowed_hosts=["freeagent-ai.avalou.co"], allowed_origins=[ORIGIN]),
    )

    @asynccontextmanager
    async def lifespan(app):
        async with manager.run():
            yield

    async def metadata(request):
        return JSONResponse(
            {
                "resource": ORIGIN + "/mcp",
                "authorization_servers": [settings.issuer],
                "scopes_supported": ["freeagent:read", "freeagent:write"],
                "bearer_methods_supported": ["header"],
            }
        )

    def session(request):
        token = request.cookies.get("__session", "")
        record = accounts.store.get("web_state", key_for(token)) if token else {}
        if record.get("kind") != "session" or record.get("expires", 0) <= time.time() or not record.get("subject"):
            raise AccessDenied("Sign in to manage your FreeAgent connection")
        return token, record

    async def home(request):
        if landing_html is not None:
            return HTMLResponse(landing_html)
        return page(
            "FreeAgent AI",
            '<p>Connect your UK FreeAgent account to ChatGPT for timesheets, draft invoices, expenses, estimates, bills, bank reconciliation and reports.</p><p><a href="/account">Manage your connection</a></p><p><a href="/privacy">Privacy</a> · <a href="/terms">Terms</a> · <a href="/support">Support</a></p>',
        )

    async def account(request):
        try:
            token, record = await anyio.to_thread.run_sync(session, request)
        except AccessDenied:
            return page(
                "Connect FreeAgent",
                '<p><a href="/login">Sign in</a> to link or disconnect your account. ChatGPT can stay connected for up to 30 days.</p>',
            )
        link = await anyio.to_thread.run_sync(accounts.store.get, "account_links", key_for(record["subject"]))
        csrf = await anyio.to_thread.run_sync(
            lambda: accounts.new_state(
                "account_action",
                {"session": token, "subject": record["subject"], "generation": link.get("generation", 0)},
            )
        )
        if record["subject"].startswith(f"oauth2|{settings.connection_name}|"):
            return page(
                "Your FreeAgent connection",
                f"<p>{'Connected' if link.get('active') else 'Disconnected'}</p>"
                f'<form method="post" action="/disconnect"><input type="hidden" name="state" value="{csrf}">'
                "<button>Disconnect FreeAgent</button></form>"
                "<p>To connect again, return to the FreeAgent AI plugin in ChatGPT.</p>",
            )
        return page(
            "Your FreeAgent connection",
            f'<p>{"Connected" if link.get("active") else "Not connected"}</p><form method="post" action="/link"><input type="hidden" name="state" value="{csrf}"><button>Link or replace FreeAgent account</button></form><form method="post" action="/disconnect"><input type="hidden" name="state" value="{csrf}"><button>Disconnect FreeAgent</button></form><p>After linking or replacement, <a href="/login">sign in again</a> and reconnect ChatGPT. Requests already sent may have completed; inspect before repeating them.</p>',
        )

    async def login(request):
        sid = secrets.token_urlsafe(32)
        nonce, code_verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        state = await anyio.to_thread.run_sync(
            lambda: accounts.new_state("auth0", {"session": sid, "nonce": nonce, "verifier": code_verifier})
        )
        challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip("=")
        query = urlencode(
            {
                "connection": settings.connection_name,
                "client_id": settings.web_client_id,
                "redirect_uri": ORIGIN + "/auth/callback",
                "response_type": "code",
                "scope": "openid",
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "prompt": "login",
                "max_age": "0",
            }
        )
        response = RedirectResponse(settings.issuer + "authorize?" + query)
        response.set_cookie("__session", sid, secure=True, httponly=True, samesite="lax", max_age=600)
        return response

    async def auth_callback(request):
        state = await anyio.to_thread.run_sync(accounts.take_state, request.query_params.get("state", ""), "auth0")
        if state["session"] != request.cookies.get("__session"):
            raise AccessDenied("Callback session mismatch; start again")
        tokens, _ = await anyio.to_thread.run_sync(
            lambda: request_json(
                "POST",
                settings.issuer + "oauth/token",
                Deadline(),
                form={
                    "grant_type": "authorization_code",
                    "code": request.query_params.get("code", ""),
                    "redirect_uri": ORIGIN + "/auth/callback",
                    "client_id": settings.web_client_id,
                    "client_secret": settings.web_client_secret,
                    "code_verifier": state["verifier"],
                },
            )
        )
        claims = await anyio.to_thread.run_sync(verifier.claims, tokens["id_token"], settings.web_client_id)
        if claims.get("nonce") != state["nonce"]:
            raise AccessDenied("Callback nonce mismatch")
        sid = await anyio.to_thread.run_sync(
            lambda: accounts.new_state(
                "session", {"subject": claims["sub"], "primary_auth_time": claims[PRIMARY_AUTH_CLAIM]}, ttl=3600
            )
        )
        response = RedirectResponse("/account")
        response.set_cookie("__session", sid, secure=True, httponly=True, samesite="lax", max_age=3600)
        return response

    async def action(request):
        if request.headers.get("origin") != ORIGIN:
            raise AccessDenied("Account action origin mismatch")
        token, record = await anyio.to_thread.run_sync(session, request)
        form = await request.form(max_fields=2, max_files=0)
        state = await anyio.to_thread.run_sync(accounts.take_state, str(form.get("state", "")), "account_action")
        if state["session"] != token or state["subject"] != record["subject"]:
            raise AccessDenied("Account action session mismatch")
        if record["subject"].startswith(f"oauth2|{settings.connection_name}|") and request.url.path != "/disconnect":
            raise AccessDenied("Connect the FreeAgent account through ChatGPT")
        if request.url.path == "/disconnect":
            await anyio.to_thread.run_sync(accounts.disconnect, record["subject"], state["generation"])
            return RedirectResponse("/account", status_code=303)
        state_token = await anyio.to_thread.run_sync(
            lambda: accounts.new_state("freeagent", {**state, "environment": settings.environment})
        )
        base = freeagent_base(settings.environment)
        return RedirectResponse(
            base
            + "approve_app?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": settings.freeagent_client_id,
                    "redirect_uri": ORIGIN + "/freeagent/callback",
                    "state": state_token,
                }
            ),
            status_code=303,
        )

    async def freeagent_callback(request):
        if await anyio.to_thread.run_sync(connect.is_callback, request):
            return await connect.callback(request)
        token, record = await anyio.to_thread.run_sync(session, request)
        state = await anyio.to_thread.run_sync(accounts.take_state, request.query_params.get("state", ""), "freeagent")
        if state["session"] != token or state["subject"] != record["subject"]:
            raise AccessDenied("Account link session mismatch")

        def link():
            stored, company = exchange_identity(
                settings,
                request.query_params.get("code", ""),
                ORIGIN + "/freeagent/callback",
                Deadline(),
                request_json,
                environment=state["environment"],
            )
            accounts.replace(record["subject"], company["url"], state["environment"], stored, state["generation"])

        await anyio.to_thread.run_sync(link)
        return page(
            "Account linked",
            '<p>Previous authorizations have been invalidated. <a href="/login">Sign in again</a>, then reconnect the FreeAgent AI plugin in ChatGPT.</p>',
        )

    async def challenge(request):
        return PlainTextResponse(settings.challenge, status_code=200 if settings.challenge else 404)

    async def policy(request):
        if landing_config is not None:
            return RedirectResponse(landing_config[request.url.path.lstrip("/") + "_url"], status_code=302)
        title, paragraphs = SITE_NOTICES[request.url.path.strip("/")]
        return page(title, "".join("<p>" + html.escape(paragraph) + "</p>" for paragraph in paragraphs))

    async def denied(request, error):
        if request.url.path.startswith("/connect/"):
            return JSONResponse({"error": "invalid_request", "error_description": str(error)}, status_code=400)
        return PlainTextResponse(str(error), status_code=400)

    async def failed(request, error):
        return PlainTextResponse(
            "Connection operation failed; start again. Inspect any submitted accounting write before retrying.",
            status_code=502,
        )

    routes = [
        *connect.routes(),
        Route("/", home),
        Mount("/landing-assets", app=StaticFiles(directory=LANDING_ROOT / "assets")),
        Route("/account", account),
        Route("/login", login),
        Route("/auth/callback", auth_callback),
        Route("/link", action, methods=["POST"]),
        Route("/disconnect", action, methods=["POST"]),
        Route("/freeagent/callback", freeagent_callback),
        Route("/.well-known/oauth-protected-resource/mcp", metadata),
        Route("/.well-known/oauth-protected-resource", metadata),
        Route("/.well-known/openai-apps-challenge", challenge),
        Route("/health", lambda request: PlainTextResponse("ok")),
        Route("/privacy", policy),
        Route("/terms", policy),
        Route("/support", policy),
    ]
    app = Starlette(routes=routes, lifespan=lifespan, exception_handlers={AccessDenied: denied, Exception: failed})
    protected = MCPAuth(manager, verifier)

    async def dispatch(scope, receive, send):
        budget = deadline_context.set(Deadline())
        try:
            if scope["type"] == "http" and scope["path"] == "/mcp":
                await protected(scope, receive, send)
            else:
                await app(scope, receive, send)
        finally:
            deadline_context.reset(budget)

    return SecurityHeaders(ScopeMirror(dispatch))


def run():
    import os

    import uvicorn

    uvicorn.run(
        create_app(), host="0.0.0.0", port=int(os.environ.get("PORT", "8080")), access_log=False, log_level="warning"
    )
