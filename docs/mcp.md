# MCP server

Typed tools over the client: `freeagent_get` (read-only), `create_timeslip`, `create_draft_invoice` (always Draft, emails off). Writes read back and return what FreeAgent holds.

The Claude Code and Codex plugins start it with `uvx` straight from GitHub (see `.mcp.json`), so no checkout or pip install is needed; `uv` must be installed. Run `freeagent-ai login` once first (e.g. `uvx --from git+https://github.com/avalou-co/freeagent-ai freeagent-ai login`); the server uses the same credentials file.

For local development: `pip install -e '.[mcp]'` and `freeagent-ai mcp`.

## ChatGPT

ChatGPT connects to remote servers only, so it needs `freeagent-ai mcp --http` (serves `http://127.0.0.1:8000/mcp`) reachable over public HTTPS, added as a custom connector in developer mode.

**The HTTP server has no authentication.** Anyone who reaches the URL can read and write your FreeAgent account. Do not expose it through a public tunnel until auth is added.
