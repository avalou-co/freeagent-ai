"""Read-only arithmetic over reviewed API snapshots; no credentials or API writes.

Amounts remain Decimal until presentation. Callers supply complete, paginated
collections and explicit scope/assumptions as described in docs/analysis.md.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

Record = dict[str, Any]


class IncompleteData(ValueError):
    """The snapshot cannot support a complete calculation; never substitute zero."""


def require_fields(rows: list[Record], fields: str, label: str) -> None:
    """Make absent required provider fields explicit before doing arithmetic."""
    for index, row in enumerate(rows):
        missing = [field for field in fields.split() if field not in row or row[field] is None]
        if missing:
            raise IncompleteData(f"Incomplete {label} row {index}: missing {', '.join(missing)}")


def number(value: str) -> Decimal:
    """Reject floats, missing data and non-finite amounts rather than guessing."""
    if not isinstance(value, str):
        raise ValueError("Amounts and hours must be decimal strings")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("Invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("Expected finite decimal")
    return result


def unique(rows: list[Record]) -> list[Record]:
    """Repeated pages must not silently inflate totals."""
    seen: set[str] = set()
    for row in rows:
        if not row["url"] or row["url"] in seen:
            raise ValueError("Source URLs must be present and unique")
        seen.add(row["url"])
    return rows


def forecast(
    *,
    start: date,
    timestamp: str,
    currency: str,
    accounts: list[Record],
    invoices: list[Record],
    bills: list[Record],
    commitments: list[Record],
    receipt_delay_days: int = 0,
    missing_inputs: list[str],
) -> Record:
    """Thirteen seven-day buckets, with overdue residuals placed at start.

    Collections are preselected for this account scope; commitments have unique
    source URLs, signed amount, date and confirmed additional=True. They must
    exclude payments already in balances or outstanding API records.
    """
    if not timestamp or not currency or not accounts:
        raise ValueError("Supply snapshot timestamp, currency and selected accounts")
    snapshot = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if snapshot.tzinfo is None or snapshot.astimezone(timezone.utc).date() != start:
        raise ValueError("Start must match the UTC snapshot date for current balances")
    if type(receipt_delay_days) is not int or receipt_delay_days < 0:
        raise ValueError("Receipt delay must be a nonnegative integer")
    require_fields(accounts, "url currency current_balance", "bank account")
    require_fields(invoices + bills, "url currency status due_value due_on", "outstanding document")
    if any(row.get("additional") is not True for row in commitments):
        raise ValueError("Commitments require confirmed additional=True")
    require_fields(commitments, "url currency date amount additional", "commitment")
    balance = Decimal(0)
    for account in unique(accounts):
        if account["currency"] != currency:
            raise ValueError("Keep currencies separate")
        balance += number(account["current_balance"])
    events: list[Record] = []
    overdue: list[str] = []
    excluded: list[str] = []
    unique(invoices + bills + commitments)
    for kind, rows, sign in (("invoice", invoices, 1), ("bill", bills, -1)):
        for row in rows:
            if row["currency"] != currency:
                raise ValueError("Keep currencies separate")
            if row["status"] not in {"Open", "Overdue", "Part written-off"}:
                excluded.append(row["url"])
                continue
            amount = number(row["due_value"])
            if amount < 0:
                raise ValueError("Refunds/credits need a reviewed signed commitment")
            due = date.fromisoformat(row["due_on"])
            if due < start and amount:
                overdue.append(row["url"])
            expected = max(start, due)
            if kind == "invoice":
                expected += timedelta(days=receipt_delay_days)
            events.append({"source": row["url"], "date": expected, "amount": amount * sign})
    for row in commitments:
        if row["currency"] != currency or row.get("additional") is not True:
            raise ValueError("Commitments require matching currency and confirmed additional=True")
        expected = date.fromisoformat(row["date"])
        if expected < start:
            raise ValueError("Past commitments require reconciliation with opening balances")
        events.append({"source": row["url"], "date": expected, "amount": number(row["amount"])})
    weeks: list[Record] = []
    first_shortfall = None
    for index in range(13):
        week_start = start + timedelta(days=index * 7)
        week_end = week_start + timedelta(days=7)
        selected = [event for event in events if week_start <= event["date"] < week_end]
        receipts = sum((e["amount"] for e in selected if e["amount"] > 0), Decimal(0))
        payments = -sum((e["amount"] for e in selected if e["amount"] < 0), Decimal(0))
        closing = balance + receipts - payments
        if first_shortfall is None and (balance < 0 or closing < 0):
            first_shortfall = week_start.isoformat()
        weeks.append(
            {
                "start": week_start.isoformat(),
                "opening": balance,
                "receipts": receipts,
                "payments": payments,
                "closing": closing,
                "sources": [e["source"] for e in selected],
            }
        )
        balance = closing
    return {
        "status": "incomplete" if missing_inputs else "complete",
        "timestamp": timestamp,
        "currency": currency,
        "accounts": [a["url"] for a in accounts],
        "receipt_delay_days": receipt_delay_days,
        "weeks": weeks,
        "first_shortfall": first_shortfall,
        "overdue": overdue,
        "excluded": excluded,
        "missing_inputs": missing_inputs,
        "outside_horizon": [e["source"] for e in events if e["date"] >= start + timedelta(days=91)],
    }


def profitability(
    *,
    start: date,
    end: date,
    timestamp: str,
    projects: list[Record],
    tasks: list[Record],
    timeslips: list[Record],
    invoices: list[Record],
    costs: list[Record],
    cost_rates: dict[str, str],
    costs_complete: bool,
    credit_notes: list[Record],
) -> Record:
    """Period activity by project; costs are reviewed signed expense/bill allocations.

    Cost rates are per user/hour in project currency (one invocation per currency).
    Revenue is issued invoice net value, never timeslip value or cash received.
    Budget usage is period activity, not lifetime remaining budget.
    """
    if end < start or not timestamp:
        raise ValueError("Supply ordered period and snapshot timestamp")
    require_fields(projects, "url contact currency", "project")
    require_fields(tasks, "url project is_billable", "task")
    require_fields(timeslips, "url project task user dated_on hours", "timeslip")
    require_fields(invoices + credit_notes, "url currency dated_on status net_value", "revenue document")
    require_fields(costs, "url dated_on currency amount", "cost allocation")
    unique(projects)
    unique(tasks)
    unique(timeslips)
    unique(invoices + credit_notes)
    unique(costs)
    task_map = {t["url"]: t for t in tasks}
    currencies = {p["currency"] for p in projects}
    if len(currencies) > 1:
        raise ValueError("Run separately per currency and rate basis")
    results: list[Record] = []
    for project in projects:
        slips = [
            t for t in timeslips if t["project"] == project["url"] and start <= date.fromisoformat(t["dated_on"]) <= end
        ]
        issued = [
            i
            for i in invoices + credit_notes
            if i.get("project") == project["url"]
            and start <= date.fromisoformat(i["dated_on"]) <= end
            and i["status"] not in {"Draft", "Scheduled To Email"}
        ]
        allocated = [
            c for c in costs if c.get("project") == project["url"] and start <= date.fromisoformat(c["dated_on"]) <= end
        ]
        if any(r["currency"] != project["currency"] for r in issued + allocated):
            raise ValueError("Invoice/cost currency differs from project")
        hours = billable = unbilled = time_cost = Decimal(0)
        unknown_rates: list[str] = []
        for slip in slips:
            h = number(slip["hours"])
            if h < 0 or slip.get("timer"):
                raise ValueError("Resolve negative time or running timers first")
            if slip["task"] not in task_map:
                raise IncompleteData("Incomplete task coverage for timeslip; resolve missing task")
            task = task_map[slip["task"]]
            if task.get("project") != project["url"] or type(task.get("is_billable")) is not bool:
                raise ValueError("Resolve task project and billability")
            hours += h
            if task["is_billable"]:
                billable += h
                if not slip.get("billed_on_invoice"):
                    unbilled += h
            rate = cost_rates.get(slip["user"])
            if rate is None:
                unknown_rates.append(slip["url"])
            else:
                value = number(rate)
                if value < 0:
                    raise ValueError("Cost rates cannot be negative")
                time_cost += h * value
        revenue = sum((number(i["net_value"]) for i in issued), Decimal(0))
        direct_cost = sum((number(c["amount"]) for c in allocated), Decimal(0))
        budget = number(project["budget"]) if project.get("budget") is not None else None
        usage = None
        if budget is not None and budget > 0:
            require_fields([project], "budget_units", "project budget")
        if budget is None or budget == 0:
            pass
        elif budget < 0:
            raise ValueError("Budget cannot be negative")
        elif project["budget_units"] == "Hours":
            usage = hours
        elif project["budget_units"] == "Days":
            require_fields([project], "hours_per_day", "day budget")
            day = number(project["hours_per_day"])
            if day <= 0:
                raise ValueError("Hours per day must be positive")
            usage = hours / day
        elif project["budget_units"] == "Monetary":
            usage = revenue
        else:
            raise ValueError("Unknown budget units")
        results.append(
            {
                "project": project["url"],
                "contact": project["contact"],
                "currency": project["currency"],
                "hours": hours,
                "billable_hours": billable,
                "unbilled_hours": unbilled,
                "invoiced_net_revenue": revenue,
                "realised_hourly_revenue": revenue / hours if hours else None,
                "time_cost": None if unknown_rates else time_cost,
                "direct_cost": direct_cost,
                "margin": revenue - time_cost - direct_cost if costs_complete and not unknown_rates else None,
                "missing_cost_rates": unknown_rates,
                "costs_complete": costs_complete,
                "period_budget_usage": usage,
                "budget": budget,
                "period_budget_fraction": usage / budget if budget and usage is not None else None,
                "sources": [r["url"] for r in slips + issued + allocated],
                "unbilled_sources": [
                    s["url"] for s in slips if not s.get("billed_on_invoice") and task_map[s["task"]]["is_billable"]
                ],
            }
        )
    project_urls = {p["url"] for p in projects}
    return {
        "status": "complete"
        if costs_complete and all(not row["missing_cost_rates"] for row in results)
        else "incomplete",
        "from": start.isoformat(),
        "to": end.isoformat(),
        "timestamp": timestamp,
        "denominator": "All recorded period hours, including non-billable time",
        "projects": results,
        "unattributed_costs": [
            c
            for c in costs
            if c.get("project") not in project_urls and start <= date.fromisoformat(c["dated_on"]) <= end
        ],
    }
