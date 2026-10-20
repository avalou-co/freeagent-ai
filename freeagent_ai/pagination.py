"""Google API Core page traversal adapted to FreeAgent Link-header responses."""

from urllib.parse import urljoin

from google.api_core.page_iterator import HTTPIterator

from .api_mechanics import api_path


def collect_pages(fetch, path, base):
    """Aggregate list fields, preserving first-page metadata and failing on incomplete reads.

    The iterator owns traversal. The adapter translates next links into opaque page
    tokens; fetch retains each transport's authentication, retry and deadline policy.
    """
    seen = set()

    def request(method, path, query_params):
        current = query_params.get("pageToken", path)
        if current in seen or len(seen) >= 1000:
            raise ValueError("Pagination incomplete: cycle or page limit exceeded")
        seen.add(current)
        payload, links = fetch(current)
        target = links.get("next", {}).get("url")
        following = api_path(urljoin(base + current, target), base) if target is not None else None
        return {"items": [payload], "nextPageToken": following}

    pages = iter(HTTPIterator(None, request, path, item_to_value=lambda _, item: item))
    result = next(pages)
    for page in pages:
        if not isinstance(result, dict) or not isinstance(page, dict):
            raise ValueError("Expected object responses for pagination")
        lists = [key for key, value in result.items() if isinstance(value, list)]
        if not lists or any(not isinstance(page.get(key), list) for key in lists):
            raise ValueError("Inconsistent pagination response")
        for key in lists:
            result[key].extend(page[key])
    return result
