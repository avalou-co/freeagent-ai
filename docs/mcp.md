# MCP server

Typed tools over the client: `freeagent_get` (read-only), `create_timeslip`, `create_draft_invoice` (always Draft, emails off). Writes read back and return what FreeAgent holds.

```bash
pip install -e '.[mcp]'
freeagent-ai login            # once; the server uses the same credentials file
```

## Claude Code

Bundled in the plugin; nothing extra to do once `freeagent-ai` is on PATH.

## Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.freeagent]
command = "freeagent-ai"
args = ["mcp"]
```

## ChatGPT

ChatGPT connects to remote servers only, so it needs `freeagent-ai mcp --http` (serves `http://127.0.0.1:8000/mcp`) reachable over public HTTPS, added as a custom connector in developer mode.

**The HTTP server has no authentication.** Anyone who reaches the URL can read and write your FreeAgent account. Do not expose it through a public tunnel until auth is added.
