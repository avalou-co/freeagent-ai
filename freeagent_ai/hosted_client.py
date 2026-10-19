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
from urllib.parse import unquote, urlencode, urljoin, urlsplit

from .client import _retry_after
from .hosted_accounts import AccessDenied
from .hosted_network import PinnedHTTPS, resolve_public, set_read_timeout, socket_budget

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
            parts, size = [], 0
            while True:
                # read1 performs at most one socket read, so slow streams cannot renew the budget.
                set_read_timeout(response, deadline)
                chunk = response.read1(65536)
                deadline.remaining()
                if not chunk:
                    break
                size += len(chunk)
                if size > 8 * 1024 * 1024:
                    raise ValueError("API response exceeds transport size limit; read incomplete")
                parts.append(chunk)
            payload = b"".join(parts)
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
        self.base = (
            "https://api.freeagent.com/v2/"
            if binding.environment == "production"
            else "https://api.sandbox.freeagent.com/v2/"
        )

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
        parsed = urlsplit(path)
        if (
            parsed.scheme
            or parsed.netloc
            or parsed.fragment
            or path.startswith("/")
            or ".." in unquote(parsed.path).split("/")
        ):
            raise ValueError("Invalid API path")
        result, headers = self._request(method, path, body)
        if method == "POST" and isinstance(result, dict):
            endpoint = parsed.path.split("/", 1)[0]
            for resource in result.values():
                url = resource.get("url", "") if isinstance(resource, dict) else ""
                prefix = self.base + endpoint + "/"
                if isinstance(url, str) and url.startswith(prefix) and url[len(prefix) :].isdigit():
                    self.last_created = url
        seen = {path}
        while method == "GET" and paginate and headers.get("Link"):
            # Use the same Link parser as the installed HTTP client, without making a request.
            import httpx2

            links = httpx2.Response(200, headers={"Link": headers["Link"]}).links
            target = links.get("next", {}).get("url")
            if target is None:
                break
            url = urljoin(self.base + path, target)
            if not url.startswith(self.base):
                raise ValueError("Pagination destination outside the FreeAgent API")
            path = url[len(self.base) :]
            check = urlsplit(path)
            if check.fragment or check.scheme or check.netloc or ".." in unquote(check.path).split("/"):
                raise ValueError("Invalid pagination link")
            if path in seen or len(seen) >= 1000:
                raise ValueError("Pagination incomplete: cycle or page limit")
            seen.add(path)
            page, headers = self._request(method, path, body)
            lists = [key for key, value in result.items() if isinstance(value, list)]
            if not lists or any(not isinstance(page.get(key), list) for key in lists):
                raise ValueError("Pagination incomplete: inconsistent response")
            for key in lists:
                result[key].extend(page[key])
        return result
