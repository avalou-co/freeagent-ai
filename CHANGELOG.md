# Changelog

Changes are grouped by release. A version heading describes the release contents;
publication is confirmed by its Git tag and GitHub Release, not by this file.

## [0.2.0]

First planned tagged release, following the initial 0.1.0 development version.
This version is unreleased until the owner tags and publishes it. Live mobile
verification and public directory publication remain pending; follow
`docs/hosted.md` and GitHub issues #33/#36.

### Added

- Contact, project and task setup workflows.
- Expense claims with receipts, supplier bills and draft estimates.
- Bank transaction review, accounting reports and read-only invoice status.
- A client setup skill alongside the eight accounting workflows, with discovery
  checks for README and agent instructions.
- Hosted per-user account connections, OAuth discovery and bounded sessions,
  including direct FreeAgent sign-in without a separate Avalou signup.
- A product landing page with privacy, terms and support pages, search discovery
  files and merged-main website delivery.
- Reproducible hosted plugin packaging with public review metadata. Directory
  submission, approval and publication remain separate steps.
- Remote receipt transport and the named public tool schema audit.

### Changed

- GET collection calls follow pagination and handle rate limits with bounded
  retries.
- Direct POST, PUT and DELETE tools pass approved payloads to FreeAgent; agents
  handle ownership, approval and readback under the documented safety rules.
- Python, Claude, Codex and generated hosted plugin versions agree at 0.2.0.

### Security

- Authenticated HTTP MCP access and fail-closed configuration.
- OAuth callback state validation, private atomic credential storage and rejection
  of authenticated redirects.
- Hosted account isolation and protected credential storage. Public launch still
  requires the live verification and owner publication steps in the hosted guide.

## [0.1.0]

Initial development version, without a tagged GitHub Release: Python API client,
OAuth login and refresh, CLI, timesheet and draft-invoice workflows, MCP server,
and local Claude/Codex plugin installation.
