"""Generation-bound FreeAgent transport with a shared monotonic deadline.

Only declared tools select paths. No operator credential file, proxy environment,
redirect following, background work or automatic retry of an uncertain write.
"""

import base64
import json
import time
import urllib.error
from contextvars import ContextVar
from email.message import Message
from io import BytesIO
from typing import Any
from urllib.parse import urlencode, urlsplit

import httpx2

from .api_mechanics import api_path
from .client import _retry_after
from .hosted_accounts import AccessDenied
from .hosted_network import PinnedHTTPS, read_bounded, resolve_public, socket_budget
from .hosted_oauth import freeagent_base
from .pagination import collect_pages

principal_context: ContextVar = ContextVar("hosted_principal")


def request_json(method, url, deadline, *, body=None, form=None, headers=None) -> tuple[Any, Message]:
    """Bounded HTTPS response; socket deadlines are renewed from the same end time."""
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise ValueError("HTTPS origin required")
    data = json.dumps(body).encode() if body is not None else (urlencode(form).encode() if form is not None else None)
    if data and len(data) > 8 * 1024 * 1024:
        raise ValueError("API request exceeds transport size limit")
    request_headers = {"Accept": "application/json", "User-Agent": "FreeAgent-AI/0.3.0", **(headers or {})}
    if data is not None:
        request_headers["Content-Type"] = (
            "application/x-www-form-urlencoded" if form is not None else "application/json"
        )
    connection = PinnedHTTPS(parsed.hostname, resolve_public(parsed.hostname, deadline), deadline)
    try:
        connection.connect()
        assert connection.sock is not None
        with socket_budget(connection.sock, deadline):
            connection.sock.settimeout(deadline.remaining())
            connection.request(
                method, parsed.path + ("?" + parsed.query if parsed.query else ""), data, request_headers
            )
            connection.sock.settimeout(deadline.remaining())
            response = connection.getresponse()
            payload = read_bounded(
                response, deadline, 8 * 1024 * 1024, "API response exceeds transport size limit; read incomplete"
            )
            message = Message()
            for name, value in response.getheaders():
                message[name] = value
            if response.status >= 300:
                # No callback query/token in error URL; callers expose only safe statuses.
                raise urllib.error.HTTPError(
                    parsed.scheme + "://" + parsed.netloc + parsed.path,
                    response.status,
                    "API request rejected",
                    message,
                    BytesIO(payload),
                )
            return json.loads(payload) if payload else response.status, message
    finally:
        connection.close()


class HostedClient:
    def __init__(self, accounts, binding, deadline, client_id, client_secret, transport=request_json):
        self.accounts, self.binding, self.deadline = accounts, binding, deadline
        self.client_id, self.client_secret, self.transport = client_id, client_secret, transport
        self.last_created = ""
        self.base = freeagent_base(binding.environment)

    def exchange(self, credentials):
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        try:
            result, _ = self.transport(
                "POST",
                self.base + "token_endpoint",
                self.deadline,
                form={"grant_type": "refresh_token", "refresh_token": credentials["refresh_token"]},
                headers={"Authorization": "Basic " + basic},
            )
        except Exception:
            raise AccessDenied("FreeAgent token refresh failed; reconnect the account") from None
        return {**credentials, **result, "expires_at": time.time() + int(result["expires_in"])}

    def _request(self, method, path, body):
        creds = self.accounts.credentials(self.binding)
        if creds.get("expires_at", 0) <= time.time() + 10:
            creds = self.accounts.refresh(self.binding, self.exchange)
        for attempt in range(4):
            self.deadline.remaining()
            self.accounts.check(self.binding)  # immediately before every outbound call, including writes
            try:
                return self.transport(
                    method,
                    self.base + path,
                    self.deadline,
                    body=body,
                    headers={"Authorization": "Bearer " + creds["access_token"]},
                )
            except urllib.error.HTTPError as error:
                if method == "GET" and error.code == 429 and attempt < 3:
                    self.deadline.sleep(_retry_after(error.headers) or 2**attempt)
                    continue
                raise
            except (TimeoutError, OSError, ValueError):
                if method != "GET":
                    raise RuntimeError(
                        "Write outcome uncertain in the original linked account; inspect it before retrying"
                    ) from None
                raise RuntimeError("Read failed or incomplete; no complete result is available") from None
        raise RuntimeError("Read rate limit exceeded")

    def call(self, method, path, body=None, *, paginate=True):
        path = api_path(path, self.base)
        parsed = urlsplit(path)
        if method == "GET" and paginate:

            def fetch(current):
                result, headers = self._request(method, current, body)
                return result, httpx2.Response(200, headers={"Link": headers.get("Link", "")}).links

            return collect_pages(fetch, path, self.base)
        result, headers = self._request(method, path, body)
        if method == "POST" and isinstance(result, dict):
            endpoint = parsed.path.split("/", 1)[0]
            for resource in result.values():
                url = resource.get("url", "") if isinstance(resource, dict) else ""
                prefix = self.base + endpoint + "/"
                if isinstance(url, str) and url.startswith(prefix) and url[len(prefix) :].isdigit():
                    self.last_created = url
        return result
