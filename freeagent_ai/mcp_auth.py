"""Bearer-token authentication for the HTTP MCP transport.

The token comes from FREEAGENT_MCP_TOKEN. HTTP mode refuses to start without a valid one (fail
closed), and every request is checked before it reaches the MCP app, so no FreeAgent call can
happen unauthenticated. Never print or log the token.
"""

import hmac
import os

TOKEN_ENV = "FREEAGENT_MCP_TOKEN"
MIN_TOKEN_LENGTH = 32


def load_token(environ=None):
    """Return the configured HTTP token, or raise ValueError if absent or too weak."""
    token = (os.environ if environ is None else environ).get(TOKEN_ENV, "")
    if len(token) < MIN_TOKEN_LENGTH or not token.isascii() or token != token.strip():
        raise ValueError(
            f"{TOKEN_ENV} must be set to a random ASCII secret of at least {MIN_TOKEN_LENGTH} characters "
            'to serve MCP over HTTP (generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))")'
        )
    return token


class BearerAuth:
    """ASGI middleware: 401 unless the request carries `Authorization: Bearer <token>`."""

    def __init__(self, app, token):
        if not token:
            raise ValueError("token required")
        self.app = app
        self._token = token.encode()

    def _authorised(self, scope):
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                scheme, _, supplied = value.partition(b" ")
                return scheme.lower() == b"bearer" and hmac.compare_digest(supplied, self._token)
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] == "lifespan":
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http" and self._authorised(scope):
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http":
            body = b"Unauthorized"
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [
                        (b"content-type", b"text/plain; charset=utf-8"),
                        (b"content-length", str(len(body)).encode()),
                        (b"www-authenticate", b"Bearer"),
                    ],
                }
            )
            await send({"type": "http.response.body", "body": body})
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
