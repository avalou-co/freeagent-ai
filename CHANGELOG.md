# Changelog

Changes are grouped by release. A version heading describes the release contents;
publication is confirmed by its Git tag and GitHub Release, not by this file.

## [0.4.0]

API-only remediation release. This entry describes the proposed contents; the
annotated tag and GitHub Release confirm source publication. Deployment, provider
sandbox verification and marketplace web/iOS installation or listing remain
separate evidence gates.

### Added

- Provider-backed recurring invoice profiles, tax-return/payment evidence and
  credit-note/reconciliation reads through named hosted operations.
- Exact expense and draft-invoice payload forwarding, including provider-supported
  invoice source inclusion, manual lines, currencies and tax fields. FreeAgent
  validates accounting inputs and calculates the returned outcomes.
- Reviewed draft credit-note creation and a narrow, separately approved allocation
  workflow for selected existing issued credits and invoices, with affected-record
  readbacks. Issuing, invoice edits and cash refunds remain excluded.
- Versioned bank-explanation attachment operations with bounded hosted file inputs
  and collection readback.
- Package-derived API-only capability checks and authenticated synthetic HTTP
  coverage for all 16 packaged skills and 77 named provider-backed operations.

### Changed

- Cash, project, report and tax workflows explain provider-returned records rather
  than promise locally derived forecasts, margins or residual commitments.
- Recurring workflows show provider-reported profiles and dates without predicting
  future billing or cash receipts. Mileage workflows approve exact provider inputs
  and report FreeAgent-calculated claims; no monetary quote is promised without a
  provider preview endpoint.
- Packaged workflows use named remote tools without requiring user-local Python,
  a shell, filesystem access or an assumed interpreter. Provider errors and missing
  evidence remain explicit; uncertain writes are not blindly replayed.
- Python, local plugin manifests, generated packages, hosted server metadata and
  HTTP User-Agent are aligned at 0.4.0.

### Removed

- Custom forecast/profitability and recurring-scenario engines, mileage preview
  arithmetic, executable client helpers and the corresponding calculation tests
  and skill promises. No server-side calculator replaces them.

## [0.3.0]

First planned tagged release, following the initial 0.1.0 development version.
This version is unreleased until the owner tags and publishes it. Live mobile
verification and public directory publication remain pending; follow
`docs/hosted.md` and GitHub issues #33/#36.

### Added

- Reviewed mileage workflow with decimal distance/rate previews, dated provider
  mileage settings, and per-journey claim creation/readback for local and hosted tools.

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
- Python, Claude, Codex and generated hosted plugin versions agree at 0.3.0.

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
