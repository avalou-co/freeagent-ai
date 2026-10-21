"""Shared API destination and safe provider-error mechanics; no accounting rules."""

import json
from urllib.parse import unquote, urlsplit


def api_path(ref, base):
    """Accept relative paths or resource URLs only within this account's API base."""
    path = ref[len(base) :] if ref.startswith(base) else ref
    parsed = urlsplit(path)
    if (
        parsed.scheme
        or parsed.netloc
        or not parsed.path
        or parsed.path.startswith("/")
        or parsed.fragment
        or ".." in unquote(parsed.path).split("/")
    ):
        raise ValueError("Invalid FreeAgent API path or destination outside the API")
    return path


def provider_error(error):
    """Expose bounded validation errors, never authentication response bodies."""
    message = f"FreeAgent HTTP {error.code}"
    if error.code in {400, 409, 422}:
        try:
            response = json.loads(error.read(8192))
            if isinstance(response, dict) and "errors" in response:
                message += ": " + json.dumps(response["errors"])
        except (ValueError, AttributeError):
            pass
    return message
