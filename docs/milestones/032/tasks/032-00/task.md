# 032-00: Sync skill documentation and plugin manifests

Tracks GitHub issue [#32](https://github.com/avalou-co/freeagent-ai/issues/32).

## Scope

List every installed skill in README Claude Code commands and AGENTS.md.
Align Claude Code and Codex plugin descriptions with the supported workflows.
Audit the marketplace manifests and documented MCP tools for consistency.
Add a CI test that catches missing skill documentation.

## Acceptance criteria

- Every `.agents/skills/*/SKILL.md` workflow appears in AGENTS.md and README commands.
- Plugin descriptions cover all currently supported workflows.
- The documented MCP tool list matches the implemented tools.
- Ruff lint, Ruff formatting, Pyright and pytest pass.

## Verification

Ruff lint and formatting passed; Pyright reported zero errors.
All 81 tests passed locally on Python 3.14, including 16 documentation checks.
GitHub CI verifies Python 3.10, 3.12 and 3.13.
