# Bank attachment API migration

Provider contracts checked 25 October 2026:
[bank transactions](https://dev.freeagent.com/docs/bank_transactions?version=2026-09-01),
[explanations](https://dev.freeagent.com/docs/bank_transaction_explanations?version=2026-09-01),
[explanation attachments](https://dev.freeagent.com/docs/bank_transaction_explanation_attachments?version=2026-09-01).
FreeAgent announces plural attachments as the default from 1 December 2026.

## Inventory and contract

| Surface | Previous assumption | Migration |
| --- | --- | --- |
| Local client/API tools | Provider default; generic responses/payloads unchanged | Explicit version header on API requests; generic tools use the separate collection |
| Hosted client | Provider default | Same explicit version on each page/write, including after refreshed credentials |
| Hosted transaction/explanation projection | Attachment evidence omitted | Legacy singular and plural safe metadata; recursively project nested explanations |
| Hosted writes | No fixed bank attachment operation | Fixed list/add/update/remove tools; one bounded file per invocation, GET collection readback |
| Expense/bill helpers | Singular attachment | Unchanged: this provider migration concerns bank explanations |
| Bank-reconcile/receipts skills | No bank receipt procedure | Explicit current-request ownership, per-change approval, collection comparison and no replay |
| Local generic responses | Raw provider data | Still raw; agent must suppress signed content URLs/bytes |

The explanation read may return only attachment references. The collection returns
metadata (`url`, `file_name`, `content_type`, `file_size`, `description`) and signed
content URLs. Hosted projections omit signed URLs, expiry and file bytes at every
nested level. Absent metadata stays absent; malformed collections cause an error.
Do not infer content identity from file name/size or report an unknown upload as
verified. Empty attachment arrays establish no files only for a complete read.

POST adds files; PUT replaces file/description by attachment URL or removes an item
with `_destroy: "true"`. The provider also documents combined/bulk changes, but
hosted tools deliberately handle one reviewed file/change per call within the
existing transport budget. Count/size/model rejection is FreeAgent's decision;
the hosted downloader retains its independent bounded transport/type checks.
There is no DELETE-item endpoint; bulk DELETE is not exposed by a named tool.

## Version decision, rollout and fallback

Opt into `2026-09-01` now through a shared client constant. Apply it only to
FreeAgent API resource calls, not OAuth authorize/token exchanges. Do not
silently negotiate versions or fall back after a write; that could replay an
uncertain mutation. Retain legacy singular reads for compatibility with fixtures
and older responses, without converting missing evidence into an empty list.

Before deploying the opt-in, obtain independent security review of the file paths
and projections, run CI and verify an authorized dedicated sandbox: no/one/multiple
files, paginated collection, add/description update/replacement/removal, parent
references, auth denial and timeout/readback reconciliation. Compare metadata and
preserve other attachments. No real accounting writes are part of automated tests.
Deploy a reviewed release, verify read-only linked-account responses first, and
perform write verification only with separately approved exact sandbox changes.
Keep operator deployment details and evidence in private deployment configuration.

If the version is rejected or metadata is incompatible, stop bank attachment
writes and retain read-error evidence without contents. Correct the contract in a
reviewed release; do not retry or remove the version header automatically. Before
1 December, reverting the opt-in commit is a possible operator-controlled temporary
rollback only after confirming the provider still serves its legacy default; it
also requires disabling the new collection writes. After the default transition,
removing the header is not a legacy fallback. Pause uploads and fix forward. Reads
can preserve either documented shape, but a partial/failed read is incomplete.

## Evidence and limits

Synthetic authenticated dispatcher/HostedClient regressions cover no/one/multiple
and legacy/plural/nested attachments, collection pagination, fixed add/update/remove,
metadata-only updates, version headers, refused/missing-scope/stale account access,
unsafe downloads, provider rejection, malformed readbacks and uncertain writes
without replay. Existing receipt downloader tests cover size/type spoofing and
network boundaries. Local HTTP fixtures verify the version on every page.

These checks do not prove the announced default changed, provider sandbox acceptance,
source-platform file ownership or deployed two-account authorization. Authorized
sandbox evidence and deployed isolation verification remain external release gates.
The invocation-only downloader has no persistent upload store or source file-ID
ownership lookup; preserve the limitations in [receipts](receipts.md).
