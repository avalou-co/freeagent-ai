# 001-00: Pagination and rate-limit handling

Issue: https://github.com/avalou-co/freeagent-ai/issues/29

## Scope

Prevent GET list calls from silently truncating results by following FreeAgent's
`Link: rel=next` headers, and expose single-page control in `freeagent_get`.
Handle GET HTTP 429 responses with bounded retries respecting `Retry-After`.
Keep financial writes free of automatic rate-limit retries.

## Acceptance criteria

- GET list results combine every linked page, preserving server-provided filters.
- Single-page access remains available through the Python client and MCP tool.
- Pagination rejects foreign API URLs, cycles and inconsistent response shapes.
- Retry-After seconds and HTTP dates are honoured within documented retry limits.
- Mocked pagination, rate-limit, token-refresh and failure regressions pass.
- API and workflow documentation explains automatic and manual pagination.

## Verification

Run `ruff check .`, `ruff format --check .`, `pyright`, and `pytest`.
Obtain independent code review and resolve all P0, P1 and P2 findings before PR submission.
