"""Frozen, individually reviewable hosted operations and response projections.

See docs/public-api.md for provider sources and unsupported operations. The dispatcher
is internal: no tool accepts an API path, method, URL destination or operation name.
"""

import json
import re
import urllib.error
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode

import jsonschema
from mcp.server.mcpserver.tools import Tool as FunctionTool
from mcp.types import CallToolResult, ListToolsResult, TextContent, Tool, ToolAnnotations
from pydantic import Field, SerializeAsAny

from . import mcp_server as local
from .api_mechanics import provider_error
from .client import request_client
from .hosted_accounts import AccessDenied
from .hosted_client import HostedClient, principal_context
from .hosted_deadline import deadline_context
from .hosted_files import download

SCALAR = {"type": ["string", "number", "boolean", "null"]}


class PublicTool(Tool):
    security_schemes: list[dict] = Field(alias="securitySchemes")


class PublicToolsResult(ListToolsResult):
    tools: list[SerializeAsAny[Tool]]


REPORT_KEYS = frozenset(
    [
        "from",
        "to",
        "income",
        "expenses",
        "operating_profit",
        "less",
        "title",
        "total",
        "retained_profit",
        "retained_profit_brought_forward",
        "retained_profit_carried_forward",
        "accounting_period_start_date",
        "as_at_date",
        "currency",
        "capital_assets",
        "accounts",
        "name",
        "nominal_code",
        "display_nominal_code",
        "total_debit_value",
        "net_book_value",
        "current_assets",
        "current_liabilities",
        "net_current_assets",
        "total_assets",
        "owners_equity",
        "category",
        "user",
        "bank_account",
        "profit_and_loss_account",
        "total_owners_equity",
        "capital_account",
        "retained_profit",
        "brought_forward",
        "carried_forward",
    ]
)


class UnverifiedWrite(RuntimeError):
    pass


def report_project(value):
    if isinstance(value, list):
        return [report_project(item) for item in value]
    if isinstance(value, dict):
        return {key: report_project(item) for key, item in value.items() if key in REPORT_KEYS}
    return value


ITEM_FIELDS = [
    "url",
    "id",
    "position",
    "description",
    "item_type",
    "quantity",
    "price",
    "total_value",
    "total_value_ex_tax",
    "sales_tax_rate",
    "category",
    "project",
    "invoice_item",
    "bill",
    "net_value",
    "sales_tax_value",
    "second_sales_tax_value",
    "second_sales_tax_rate",
    "sales_tax_status",
    "second_sales_tax_status",
]
ATTACHMENT_FIELDS = ["url", "file_name", "content_type", "file_size", "description"]
TAX_PAYMENT_FIELDS = ["label", "due_on", "amount_due", "status"]
TAX_RETURNS = {
    "vat_returns": "vat_return",
    "corporation_tax_returns": "corporation_tax_return",
    "users/{user_id}/self_assessment_returns": "self_assessment_return",
}
TAX_FIELDS = "url period_starts_on period_ends_on filing_due_on filing_status filed_at filed_reference"
FIELDS = {
    "vat_return": TAX_FIELDS + " payments",
    "corporation_tax_return": TAX_FIELDS + " amount_due payment_due_on payment_status",
    "self_assessment_return": TAX_FIELDS + " payments",
    "contact": "url organisation_name first_name last_name status default_payment_terms_in_days account_balance country",
    "project": "url contact name status currency normal_billing_rate billing_period budget budget_units hours_per_day",
    "task": "url project name status billing_rate billing_period is_billable currency is_deletable",
    "user": "url first_name last_name role permission_level",
    "category": "url description nominal_code allowable_for_tax auto_sales_tax_rate",
    "timeslip": "url user project task dated_on hours comment billed_on_invoice timer",
    "invoice": "url contact contact_name project reference dated_on due_on status currency net_value sales_tax_value total_value due_value paid_value payment_terms_in_days send_new_invoice_emails send_reminder_emails send_thank_you_emails invoice_items",
    "recurring_invoice": "url contact contact_name project reference dated_on frequency recurring_status next_recurs_on recurring_end_date currency exchange_rate net_value sales_tax_value total_value payment_terms_in_days invoice_items",
    "credit_note": "url contact project reference dated_on due_on status currency exchange_rate payment_terms_in_days net_value sales_tax_value total_value due_value second_sales_tax_value refunded_value refunded_on written_off_date credit_note_items",
    "credit_note_reconciliation": "url credit_note invoice dated_on currency gross_value exchange_rate",
    "expense": "url user category dated_on gross_value description receipt_reference sales_tax_rate sales_tax_value currency attachment mileage vehicle_type engine_type engine_size reclaim_mileage initial_rate_mileage reclaim_mileage_rate rebill_mileage_rate have_vat_receipt project rebill_to_project rebill_type rebill_factor rebilled_on_invoice native_gross_value native_sales_tax_value manual_sales_tax_amount second_sales_tax_rate sales_tax_status second_sales_tax_status",
    "bill": "url contact reference dated_on due_on status currency total_value due_value net_value sales_tax_value second_sales_tax_value bill_items attachment project rebill_to_project rebill_type rebill_factor",
    "estimate": "url contact project reference dated_on status currency net_value sales_tax_value total_value estimate_items",
    "bank_account": "url name type currency current_balance latest_activity_date is_personal status",
    "bank_transaction": "url bank_account dated_on amount description unexplained_amount attachment attachments bank_transaction_explanations",
    "bank_transaction_explanation": "url bank_transaction dated_on gross_value category paid_invoice paid_bill description is_deletable attachment attachments",
    "company": "url name currency type sales_tax_registration_status",
}
RESOURCES = {
    # endpoint, singular, supported collection query parameters
    "contacts": ("contact", "view"),
    "projects": ("project", "contact view"),
    "tasks": ("task", "project view"),
    "users": ("user", ""),
    "categories": ("category", ""),
    "timeslips": ("timeslip", "from_date to_date user project task view"),
    "credit_notes": ("credit_note", "view contact project updated_since sort nested_credit_note_items"),
    "credit_note_reconciliations": ("credit_note_reconciliation", "from_date to_date updated_since"),
    "invoices": ("invoice", "view contact project updated_since"),
    "recurring_invoices": ("recurring_invoice", "view contact"),
    "expenses": ("expense", "from_date to_date user project view"),
    "bills": ("bill", "view contact from_date to_date"),
    "estimates": ("estimate", "view contact project"),
    "bank_accounts": ("bank_account", ""),
    "bank_transactions": ("bank_transaction", "bank_account view from_date to_date"),
    # Bank-account-filtered explanation collection is not exposed by this inventory.
}
CREATES = {
    "create_contact": "contact",
    "create_timeslip": "timeslip",
    "create_draft_invoice": "invoice",
    "create_draft_credit_note": "credit_note",
    "create_credit_note_reconciliation": "credit_note_reconciliation",
    "create_expense": "expense",
    "create_mileage_expense": "expense",
    "create_project": "project",
    "create_task": "task",
    "create_draft_estimate": "estimate",
    "create_bill": "bill",
    "explain_bank_transaction": "bank_transaction_explanation",
}
CORRECTIONS = {
    "contacts": ("contact", True, True),
    "projects": ("project", True, True),
    "tasks": ("task", True, False),  # Provider DELETE docs point at users/:id; never infer it.
    "timeslips": ("timeslip", True, True),
    "invoices": ("invoice", True, True),
    "expenses": ("expense", True, True),
    "bills": ("bill", True, True),
    "estimates": ("estimate", True, True),
    "bank_transaction_explanations": ("bank_transaction_explanation", False, True),
}
REFERENCE_RESOURCES = {
    "contact": "contacts",
    "project": "projects",
    "task": "tasks",
    "user": "users",
    "category": "categories",
    "bank_account": "bank_accounts",
    "bank_transaction": "bank_transactions",
    "invoice": "invoices",
    "credit_note": "credit_notes",
    "paid_invoice": "invoices",
    "paid_bill": "bills",
}


def object_schema(properties, required=()):
    return {"type": "object", "properties": properties, "required": list(required), "additionalProperties": False}


def record_schema(root):
    props = {}
    for field in FIELDS[root].split():
        if field == "payments":
            props[field] = {"type": "array", "items": object_schema({name: SCALAR for name in TAX_PAYMENT_FIELDS})}
        elif field.endswith("_items"):
            props[field] = {"type": "array", "items": object_schema({name: SCALAR for name in ITEM_FIELDS})}
        elif field == "timer":
            props[field] = {
                "anyOf": [
                    object_schema(
                        {"running": {"type": "boolean"}, "start_from": {"type": "string"}}, ["running", "start_from"]
                    ),
                    {"type": "null"},
                ]
            }
        elif field == "bank_transaction_explanations":
            props[field] = {"type": "array", "items": record_schema("bank_transaction_explanation")}
        elif field == "attachments":
            props[field] = {"type": "array", "items": object_schema({name: SCALAR for name in ATTACHMENT_FIELDS})}
        elif field == "attachment":
            props[field] = {"anyOf": [object_schema({name: SCALAR for name in ATTACHMENT_FIELDS}), {"type": "null"}]}
        else:
            props[field] = SCALAR
    return object_schema(props)


def project_attachments(value):
    """Reject incomplete collection shapes before projecting private provider fields."""
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("Attachment collection is malformed; read incomplete")
    return [{key: item[key] for key in ATTACHMENT_FIELDS if key in item} for item in value]


def project_record(record: Any, root):
    if not isinstance(record, dict):
        raise ValueError("Resource response is malformed; read incomplete")
    result = {}
    for field in FIELDS[root].split():
        if field not in record:
            continue
        value = record[field]
        if field == "payments":
            value = [{key: item[key] for key in TAX_PAYMENT_FIELDS if key in item} for item in value]
        elif field.endswith("_items"):
            value = [{key: item[key] for key in ITEM_FIELDS if key in item} for item in value]
        elif field == "timer" and value is not None:
            value = {key: value[key] for key in ("running", "start_from") if key in value}
        elif field == "bank_transaction_explanations":
            if not isinstance(value, list):
                raise ValueError("Explanation collection is malformed; read incomplete")
            value = [project_record(item, "bank_transaction_explanation") for item in value]
        elif field == "attachments":
            value = project_attachments(value)
        elif field == "attachment" and value is not None:
            if not isinstance(value, dict):
                raise ValueError("Attachment response is malformed; read incomplete")
            value = {key: value[key] for key in ATTACHMENT_FIELDS if key in value}
        result[field] = value
    return result


@dataclass(frozen=True)
class Operation:
    name: str
    method: str
    endpoint: str
    root: str
    descriptor: Tool
    helper: str = ""


def make_registry():
    registry = {}

    def add(name, method, endpoint, root, schema, output, description, helper="", meta=None):
        schemes = [{"type": "oauth2", "scopes": ["freeagent:read" if method == "GET" else "freeagent:write"]}]
        registry[name] = Operation(
            name,
            method,
            endpoint,
            root,
            PublicTool(
                name=name,
                description=description,
                input_schema=schema,
                output_schema=output,
                securitySchemes=schemes,
                annotations=ToolAnnotations(
                    read_only_hint=method == "GET",
                    destructive_hint=method in {"PUT", "DELETE"}
                    or name in {"explain_bank_transaction", "create_credit_note_reconciliation"},
                    open_world_hint=name == "update_invoice",
                    idempotent_hint=method == "GET",
                ),
                _meta={
                    "securitySchemes": schemes,
                    **(meta or {}),
                },
            ),
            helper,
        )

    id_schema = {"type": "string", "pattern": "^[0-9]+$"}
    for endpoint, (root, query) in RESOURCES.items():
        read_metadata = {"collected_at": {"type": "string"}} if root == "recurring_invoice" else {}
        params: dict = {name: {"type": "string"} for name in query.split()}
        params.update(
            per_page={"type": "integer", "minimum": 1, "maximum": 100},
            page={"type": "integer", "minimum": 1},
            paginate={"type": "boolean"},
        )
        add(
            "list_" + endpoint,
            "GET",
            endpoint,
            root,
            object_schema(params),
            object_schema(
                {endpoint: {"type": "array", "items": record_schema(root)}, **read_metadata},
                [endpoint, *read_metadata],
            ),
            f"List {endpoint.replace('_', ' ')} from the linked company. Use focused filters. Lists aggregate linked pages unless paginate is false; an incomplete read raises.",
        )
        add(
            "get_" + root,
            "GET",
            endpoint + "/{id}",
            root,
            object_schema({"id": id_schema}, ["id"]),
            object_schema({root: record_schema(root), **read_metadata}, [root, *read_metadata]),
            f"Read one {root.replace('_', ' ')} by its numeric ID.",
        )
    for name, endpoint, root in [
        ("get_current_user", "users/me", "user"),
        ("get_company", "company", "company"),
        ("get_bank_transaction_explanation", "bank_transaction_explanations/{id}", "bank_transaction_explanation"),
    ]:
        add(
            name,
            "GET",
            endpoint,
            root,
            object_schema({"id": id_schema}, ["id"]) if "{id}" in endpoint else object_schema({}),
            object_schema({root: record_schema(root)}, [root]),
            f"Read the linked company's {root.replace('_', ' ')}.",
        )
    # The versioned provider collection separates attachment changes from explanations.
    # One file per write keeps the existing bounded invocation-only upload contract.
    attachment_output = object_schema(
        {"attachments": {"type": "array", "items": object_schema({name: SCALAR for name in ATTACHMENT_FIELDS})}},
        ["attachments"],
    )
    file_schema = object_schema(
        {key: {"type": "string"} for key in ("download_url", "file_id", "mime_type", "file_name")},
        ["download_url", "file_id"],
    )
    for action, method in [("list", "GET"), ("add", "POST"), ("update", "PUT"), ("remove", "PUT")]:
        props = {"id": id_schema}
        required = ["id"]
        if action != "list":
            props["confirmed"] = {"type": "boolean"}
            required.append("confirmed")
        if action in {"update", "remove"}:
            props["attachment_id"] = id_schema
            required.append("attachment_id")
        if action in {"add", "update"}:
            props["file"] = file_schema
            props["description"] = {"type": "string"}
        if action == "add":
            required.append("file")
        name = action + "_bank_transaction_explanation_attachment" + ("s" if action == "list" else "")
        add(
            name,
            method,
            "bank_transaction_explanations/{id}/attachments",
            "attachments",
            object_schema(props, required),
            attachment_output,
            "Read attachment metadata, or change one attachment only on an explanation created during this user request. "
            "Updates/removals also require attachment ownership in this request. Show exact file/description/ID change and "
            "obtain approval before writes. Reads back the collection automatically; inspect uncertain outcomes before retry. "
            "Signed content URLs and bytes are not returned.",
            meta={"openai/fileParams": ["file"]} if action in {"add", "update"} else None,
        )
    # Tax returns use period end dates, not numeric record IDs; income tax is user-scoped.
    period_schema = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}
    for endpoint, root in TAX_RETURNS.items():
        collection = root + "s"
        scope = {"user_id": id_schema} if "{user_id}" in endpoint else {}
        add(
            "list_" + collection,
            "GET",
            endpoint,
            root,
            object_schema(
                {
                    **scope,
                    "per_page": {"type": "integer", "minimum": 1, "maximum": 100},
                    "page": {"type": "integer", "minimum": 1},
                    "paginate": {"type": "boolean"},
                },
                scope,
            ),
            object_schema({collection: {"type": "array", "items": record_schema(root)}}, [collection]),
            "Read tax returns and provider payment/filing evidence. Tax, Accounting & Users access required; unavailable or denied data is not zero. Lists aggregate all linked pages.",
        )
        add(
            "get_" + root,
            "GET",
            endpoint + "/{period_ends_on}",
            root,
            object_schema({**scope, "period_ends_on": period_schema}, [*scope, "period_ends_on"]),
            object_schema({root: record_schema(root)}, [root]),
            "Read a tax return by period end date. Filing dates are not payment deadlines; amounts/status do not prove an unpaid balance after partial payments.",
        )
    # Reports are recursive accounting values only; omit provider debug/identity keys.
    report_schema = {"type": "object", "additionalProperties": True}
    for name, endpoint, root, dates in [
        (
            "get_profit_and_loss",
            "accounting/profit_and_loss/summary",
            "profit_and_loss_summary",
            ["from_date", "to_date"],
        ),
        ("get_balance_sheet", "accounting/balance_sheet", "balance_sheet", ["as_at_date"]),
        ("get_trial_balance", "accounting/trial_balance/summary", "trial_balance_summary", ["from_date", "to_date"]),
    ]:
        add(
            name,
            "GET",
            endpoint,
            root,
            object_schema({key: {"type": "string"} for key in dates}, dates),
            object_schema(
                {root: {"type": "array", "items": report_schema} if root == "trial_balance_summary" else report_schema},
                [root],
            ),
            "Read this accounting report for the supplied dates. Ask for accounting periods; never guess.",
        )
    for helper, root in CREATES.items():
        schema = FunctionTool.from_function(getattr(local, helper)).parameters
        schema["additionalProperties"] = False
        if helper == "create_project":
            schema["properties"]["budget"]["description"] = "Decimal budget; omit or use zero for no budget."
            schema["properties"]["budget_units"]["description"] = (
                "FreeAgent budget units: Hours, Days or Monetary. Required upstream even with no budget; defaults to Days."
            )
        schema["properties"]["confirmed"] = {
            "type": "boolean",
            "description": "Agent assertion that the user approved the exact write plan.",
        }
        schema.setdefault("required", []).append("confirmed")
        meta = {}
        for path in ["receipt_path", "attachment_path"]:
            if path in schema["properties"]:
                del schema["properties"][path]
                file_key = "receipt" if path == "receipt_path" else "attachment"
                schema["properties"][file_key] = object_schema(
                    {
                        "download_url": {"type": "string"},
                        "file_id": {"type": "string"},
                        "mime_type": {"type": "string"},
                        "file_name": {"type": "string"},
                    },
                    ["download_url", "file_id"],
                )
                meta["openai/fileParams"] = [file_key]
        add(
            helper,
            "POST",
            next(key for key, value in {**CORRECTIONS, **RESOURCES}.items() if value[0] == root),
            root,
            schema,
            object_schema(
                {
                    key: record_schema(key)
                    for key in (
                        [root, "credit_note", "invoice"] if helper == "create_credit_note_reconciliation" else [root]
                    )
                },
                [root, "credit_note", "invoice"] if helper == "create_credit_note_reconciliation" else [root],
            ),
            f"{helper.replace('_', ' ').capitalize()} after showing the exact plan and obtaining approval. Resource reference inputs are numeric IDs. FreeAgent validates accounting. Reads back automatically; investigate failed readback before another create."
            + (
                " Narrow ownership exception: allocate only a selected existing issued credit to a selected invoice after complete related-credit/balance reads, exact amount/date/currency preview with provider-returned balances or explicitly user-supplied expectations (never calculated balances), and separate approval. No issuing, invoice edits, cash refunds or unrelated changes. Draft approval is not allocation approval."
                if helper == "create_credit_note_reconciliation"
                else ""
            ),
            helper,
            meta,
        )
    add(
        "get_mileage_settings",
        "GET",
        "expenses/mileage_settings",
        "mileage_settings",
        object_schema({}),
        object_schema(
            {
                "mileage_settings": object_schema(
                    {
                        "engine_type_and_size_options": {"type": "array", "items": {"type": "object"}},
                        "mileage_rates": {"type": "array", "items": {"type": "object"}},
                    }
                )
            },
            ["mileage_settings"],
        ),
        "Read date-specific provider mileage rates, thresholds and engine options. Select the journey's date; never assume a universal rate or cumulative mileage.",
    )
    for endpoint, (root, update, delete) in CORRECTIONS.items():
        for verb, method, enabled in [("update", "PUT", update), ("delete", "DELETE", delete)]:
            if not enabled:
                continue
            props = {"id": id_schema, "confirmed": {"type": "boolean"}}
            if method == "PUT":
                props["body"] = {
                    "type": "object",
                    "description": f"Exact FreeAgent payload with root {root}; sent unchanged.",
                }
            output = (
                object_schema({"status": {"type": "integer"}, "resource": {"type": "string"}}, ["status", "resource"])
                if method == "DELETE"
                else object_schema({root: record_schema(root)}, [root])
            )
            add(
                verb + "_" + root,
                method,
                endpoint + "/{id}",
                root,
                object_schema(props, list(props)),
                output,
                f"{verb.capitalize()} this {root.replace('_', ' ')} only if created during this user request and the exact correction was approved. FreeAgent validates the payload. Read back the resource or parent; an HTTP success alone does not verify deletion.",
            )
    return registry


REGISTRY = make_registry()


class Dispatcher:
    def __init__(
        self, accounts, client_id, client_secret, file_hosts=frozenset(), client_factory: Callable = HostedClient
    ):
        self.accounts, self.client_id, self.client_secret = accounts, client_id, client_secret
        self.file_hosts, self.client_factory = file_hosts, client_factory

    def invoke(self, name, arguments):
        if name not in REGISTRY:
            raise AccessDenied("Tool not available")
        operation = REGISTRY[name]
        jsonschema.validate(arguments, operation.descriptor.input_schema)
        principal = principal_context.get()
        required = "freeagent:read" if operation.method == "GET" else "freeagent:write"
        if required not in principal.scopes:
            raise AccessDenied("Required authorization scope missing")
        if operation.method != "GET" and arguments.get("confirmed") is not True:
            raise AccessDenied("Show the exact plan and obtain user approval first")
        binding = self.accounts.bind(principal)
        self.accounts.limit(principal.subject)
        client = self.client_factory(self.accounts, binding, deadline_context.get(), self.client_id, self.client_secret)
        token = request_client.set(client)
        try:
            result = self._run(operation, dict(arguments), client)
            jsonschema.validate(result, operation.descriptor.output_schema)
            return result
        except Exception:
            if client.last_created:
                raise UnverifiedWrite(
                    f"Created {client.last_created} in original company {binding.company}; readback was not verified. Inspect this resource before any retry."
                ) from None
            raise
        finally:
            request_client.reset(token)

    def _run(self, op, args, client):
        args.pop("confirmed", None)
        if op.root == "attachments":
            return self._attachments(op, args, client)
        if op.helper:
            file = args.pop("receipt", args.pop("attachment", None))
            if file is not None:
                attachment = download(file, self.file_hosts, client.deadline)
                original = client.call

                def attach(method, path, body=None, **kwargs):
                    if method == "POST":
                        if not isinstance(body, dict):
                            raise ValueError("Expected resource payload")
                        body = {**body, op.root: {**body[op.root], "attachment": attachment}}
                    return original(method, path, body, **kwargs)

                client.call = attach
            self._expand_references(args, client.base)
            # No filesystem parameter exists in the public schema.
            result = getattr(local, op.helper)(**args)
            roots = (
                [op.root, "credit_note", "invoice"] if op.helper == "create_credit_note_reconciliation" else [op.root]
            )
            return {root: project_record(result[root], root) for root in roots}
        path = op.endpoint.replace("{id}", args.pop("id", ""))
        for parameter in ("user_id", "period_ends_on"):
            if "{" + parameter + "}" in path:
                path = path.replace("{" + parameter + "}", args.pop(parameter))
        paginate = args.pop("paginate", True)
        if op.name.startswith("list_"):
            args.setdefault("per_page", 100)
        body = args.pop("body", None)
        self._expand_references(args, client.base)
        if args:
            path += "?" + urlencode(args)
        result = client.call(op.method, path, body, paginate=paginate)
        if op.method == "DELETE":
            return {"status": result if isinstance(result, int) else 200, "resource": client.base + path}
        if op.method == "PUT":
            result = client.call("GET", path)
        if op.name.startswith("list_"):
            collection = op.root + "s" if op.endpoint in TAX_RETURNS else op.endpoint
            records: dict[str, Any] = {collection: [project_record(item, op.root) for item in result[collection]]}
            if op.root == "recurring_invoice":
                records["collected_at"] = datetime.now(timezone.utc).isoformat()
            return records
        if op.endpoint.startswith("accounting/"):
            # Reports contain accounting summaries, no user profile or credential data.
            return {op.root: report_project(result[op.root])}
        if op.name == "get_mileage_settings":
            settings = result[op.root]
            # Only provider accounting settings, not unrelated response metadata.
            return {
                op.root: {
                    key: settings[key] for key in ("engine_type_and_size_options", "mileage_rates") if key in settings
                }
            }
        if op.root == "credit_note_reconciliation" and op.root not in result:
            # Provider detail JSON documents a plural root, unlike XML/create.
            result = {op.root: result["credit_note_reconciliations"]}
        record: dict[str, Any] = {op.root: project_record(result[op.root], op.root)}
        if op.root == "recurring_invoice":
            record["collected_at"] = datetime.now(timezone.utc).isoformat()
        return record

    def _attachments(self, op, args, client):
        path = op.endpoint.replace("{id}", args.pop("id"))
        if op.method != "GET":
            item = {}
            if "attachment_id" in args:
                item["url"] = client.base + "attachments/" + args.pop("attachment_id")
            if op.name.startswith("remove_"):
                item["_destroy"] = "true"
            else:
                file = args.pop("file", None)
                if file is not None:
                    item.update(download(file, self.file_hosts, client.deadline))
                if "description" in args:
                    item["description"] = args["description"]
            client.call(op.method, path, {"attachments": [item]})
            try:
                result = client.call("GET", path)
                projected = {"attachments": project_attachments(result["attachments"])}
                jsonschema.validate(projected, op.descriptor.output_schema)
                return projected
            except Exception:
                raise UnverifiedWrite(
                    "Attachment write returned success but collection readback was not verified. "
                    f"Inspect {client.base + path} in the original linked company before any retry."
                ) from None
        else:
            result = client.call("GET", path)
        return {"attachments": project_attachments(result["attachments"])}

    @staticmethod
    def _expand_references(args, base):
        for key, resource in REFERENCE_RESOURCES.items():
            if args.get(key):
                if not re.fullmatch(r"[0-9]+", args[key]):
                    raise ValueError("Resource references must be numeric IDs")
                args[key] = base + resource + "/" + args[key]

    def call_tool(self, name, arguments):
        try:
            data = self.invoke(name, arguments)
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(data))], structured_content=data)
        except UnverifiedWrite as error:
            message = str(error)
        except (AccessDenied, ValueError, jsonschema.ValidationError) as error:
            message = (
                str(error)
                if isinstance(error, AccessDenied)
                else "Invalid tool input or provider response; no verified result"
            )
        except local.ToolError as error:
            # Existing convenience helpers expose bounded provider validation errors.
            message = (
                str(error)
                if str(error).startswith("FreeAgent HTTP ")
                else "Provider operation failed; inspect before retrying"
            )
        except urllib.error.HTTPError as error:
            # Attachment validation responses may echo bytes or signed source URLs.
            message = (
                f"FreeAgent HTTP {error.code}"
                if name in REGISTRY and REGISTRY[name].root == "attachments"
                else provider_error(error)
            )
            message += "; inspect the original account before retrying a write"
        except Exception:
            message = (
                "Operation failed or write outcome/readback uncertain; inspect the original account before retrying"
            )
        if name in REGISTRY and REGISTRY[name].method == "GET":
            message = "Read incomplete; do not calculate from missing data or substitute zero. " + message
        return CallToolResult(content=[TextContent(type="text", text=message)], is_error=True)


def audit():
    return [
        {
            "method": operation.method,
            "endpoint": operation.endpoint,
            **operation.descriptor.model_dump(by_alias=True, exclude_none=True),
        }
        for operation in REGISTRY.values()
    ]
