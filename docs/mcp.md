# MCP server

The server wraps the Python client in typed tools:

| Tool | Does |
|------|------|
| `freeagent_get`, `find_contacts` | Read only |
| `create_contact`, `create_project`, `create_task`, `create_timeslip` | Create one entry |
| `create_draft_invoice` | Draft invoice with emails off |
| `create_draft_estimate` | Draft estimate, never sent |
| `create_expense` | Expense with an optional receipt file |
| `create_bill` | Supplier bill with line items and an optional attachment |

Each write tool reads the entry back and returns what FreeAgent holds.

## Running it

The Claude Code and Codex plugins start the server with `uvx` from GitHub (see `.mcp.json`), so you only need `uv` installed. Log in once first; the server shares the same credentials file:

```bash
uvx --from git+https://github.com/avalou-co/freeagent-ai freeagent-ai login
```

For local development, run `pip install -e '.[mcp]'` then `freeagent-ai mcp`.

## ChatGPT and remote HTTP

ChatGPT only connects to remote servers. Run `freeagent-ai mcp --http`, which serves `http://127.0.0.1:8000/mcp`, expose it over public HTTPS and add it as a custom connector in developer mode.

HTTP mode needs a bearer token. Set `FREEAGENT_MCP_TOKEN` to a random secret of 32 or more ASCII characters, or the server will not start. Requests without `Authorization: Bearer <token>` get a 401 before any FreeAgent call. stdio mode needs no token.

```bash
export FREEAGENT_MCP_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
freeagent-ai mcp --http
```

`Keeping it safe:`

- Keep the default `--host 127.0.0.1` and expose the server only through an HTTPS tunnel or reverse proxy. Plain HTTP would send the token in the clear.
- Anyone with the token can read and write your FreeAgent account. Keep it out of shell history, repos and logs, and restart with a new one if it may have leaked.
- Your connector must be able to send a custom `Authorization` header. If it cannot, do not use remote mode.
- The token is one shared secret, not OAuth. Get a security review before you rely on it.
