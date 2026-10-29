# Marketplace capability contract

The product exposes FreeAgent functionality through named remote tools. FreeAgent
owns accounting calculations and validation. Hosted code owns authentication,
account isolation, fixed API requests, serialization, pagination, bounded file
handling and provider readback. Skills gather inputs, obtain approval and explain
provider evidence. An unavailable provider capability remains unsupported.

## All implementations

Every current and future skill, tool, document and artifact change must preserve
interpreter-free ChatGPT web/mobile workflows. No client Python, shell, CLI, local
filesystem or assumed runtime is permitted. Backend code performs API mechanics;
workflows use discovered named remote tools and documented supported host artifact
transports. Unsupported delivery stays unavailable in discovery, packages and
claims. Developer/CI interpreter execution is not client compatibility evidence.
Independent architecture/client-contract review is required; installed web/mobile
observations remain separate from synthetic package/HTTP tests. See
the repository MCP design contract and contributor guidance.

## Packaging and CI gate

Both archive builders run the same contract validation, including draft builds.
CI runs `python -m freeagent_ai.package_contract` as a mandatory lint-job step
on every pull request and main push, without a path filter or continue-on-error.
That is a contributor/CI check, not a command for the marketplace-installed user.
The generated `docs/capabilities.json` records, for each shipped skill:

- A digest of the actual generated workflow, excluding the inventory appendix.
- Its required entry points and all referenced named operations with current
  input/output schemas, method, fixed provider route and approval parameter.
- Linked evidence documents and supported transport artifacts. Current workflows
  return provider JSON and explanations; receipt inputs are host file references.
  Document output uses registered MCP Apps UI -> original-account delegated HTTPS PDF attachment.
- `docs/unsupported-capabilities.json` records outstanding installed-client verification for document delivery.
  The embedded-blob prototype is rejected by the operation gate. The reviewed document
  UI/HTTPS source contract is distinct from actual installed web/mobile acceptance;
  the latter remains explicitly pending before claiming delivery.

Validation rejects missing entry points, unknown tools, API-executor instructions,
required client runtimes, executable package helpers, removed engine sources,
calculation-only descriptors, missing internal links/anchors and incomplete or
incorrect canonical source digests. Prohibitions on local execution are allowed;
CI-runner Python and provider report fields are not custom accounting features.
Canonical skill identifiers retained for compatibility do not authorize analytics.

All workflows use named provider operations. User files remain untrusted evidence;
file inputs use the bounded hosted downloader. A base64 blob, bearer-only signed URL or server
filesystem path alone is not a supported user-facing document delivery mechanism.
Introducing file output requires a reviewed artifact contract and actual client
transport verification; metadata alone does not create an output capability.

## Synthetic execution evidence

`tests/test_marketplace_contract.py` exercises every skill's required entry points
through generated package coverage, authenticated HTTP discovery and invocation,
the real dispatcher/client and synthetic provider transport. It also checks scope
refusal, write confirmation, provider failures, missing fields, automatic readback
and uncertain outcomes without write replay. Feature tests separately cover
pagination, nested payloads and bounded file-input security. No live writes are
needed for these fixtures.

The gate is a structural regression check for the audited defects. Pattern checks
cannot prove the meaning of arbitrary prose or that code with an innocent name
contains no new accounting algorithm. Provider-route/helper changes, new skills
and capabilities still require independent architecture and security review.
A name resolving in discovery or a helper imported in a test is not end-to-end
product evidence. Broadening the tests or inventory does not grant user approval.

## Separate release evidence

Synthetic API fixtures establish code/package reachability, not provider accounting
acceptance, assistant compliance, source-platform file ownership, deployed account
isolation or a real marketplace installation. Record those observations separately.
No passing gate implies public submission approval, marketplace listing or actual
ChatGPT web/iOS availability. Unsupported operations and outstanding live evidence
must remain visible in release notes and the relevant publication work.
