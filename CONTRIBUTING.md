# Contributing

Read [agent rules](docs/agent-rules.md) and the [MCP design contract](docs/mcp.md#design-contract)
before changing implementation, skills or documentation. Track development work in
GitHub issues and Projects; keep public changes free of customer/deployment data.

Every current and future shipped plugin workflow must work in ChatGPT on web and
mobile without a client interpreter, Python, shell, CLI, local filesystem or assumed
runtime. Use discovered named remote provider tools and documented supported host
input/output artifact transports. Backend code performs API mechanics only; it
must not replace FreeAgent accounting calculations or validation.

Before review, run Ruff lint/format, Pyright, pytest and the mandatory CI capability
gate (`python -m freeagent_ai.package_contract`) in the contributor environment.
The existing CI lint job runs that gate on every PR and main push; do not make it
optional or bypass it for skill, tool, artifact or documentation changes.

Independent reviewers must trace the actual generated skill to discovered named
tools, authenticated remote calls, provider responses and a usable client result.
Review permissions, missing/error states and supported artifact transport alongside
approval, ownership, readback and uncertain-write behavior. Developer/CI tests
using an interpreter prove server/package behavior, not client runtime support.
Record actual installed web/mobile verification separately before claiming client
artifact delivery. Never infer support from an embedded blob or metadata alone.

When a provider operation or client output path is unsupported, fail closed: omit
it from hosted discovery and packages, record the capability as unavailable and
keep user-facing claims accurate. Preserve clearly separated experimental diagnostics
without shipping them as a supported workflow. Human review and merging are required.
