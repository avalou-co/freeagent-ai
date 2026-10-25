"""Read-only scenarios over reviewed recurring profiles; no provider mutations.

Cadence and payment assumptions are scenario inputs, not promises about provider
scheduling or collections. Generated-invoice relationships require reviewed evidence.
"""

from calendar import monthrange
from datetime import date, datetime
from typing import Any

from .analysis import IncompleteData, number, require_fields, unique

WEEKS = {"Weekly": 1, "Two Weekly": 2, "Four Weekly": 4}
MONTHS = {"Monthly": 1, "Two Monthly": 2, "Quarterly": 3, "Biannually": 6, "Annually": 12, "2-Yearly": 24}


def _scheduled(anchor: date, index: int, frequency: str) -> date:
    """Clamp each month independently to the reviewed anchor day (no drift)."""
    from datetime import timedelta

    if frequency in WEEKS:
        return anchor + timedelta(weeks=WEEKS[frequency] * index)
    months = anchor.year * 12 + anchor.month - 1 + MONTHS[frequency] * index
    year, month = divmod(months, 12)
    return date(year, month + 1, min(anchor.day, monthrange(year, month + 1)[1]))


def billing_dates(profile: dict[str, Any], *, end: date, anchor: date) -> list[date]:
    """Expand from provider next date using an explicitly reviewed cadence anchor.

    The horizon is inclusive. A provider end date is treated as inclusive for the
    scenario only, which must be confirmed by the caller. Unsupported schedules or
    a next date inconsistent with the chosen anchor are incomplete, never guessed.
    """
    frequency = profile["frequency"]
    if frequency not in WEEKS and frequency not in MONTHS:
        raise IncompleteData("Unsupported recurrence frequency")
    next_date = date.fromisoformat(profile["next_recurs_on"])
    if anchor > next_date:
        raise IncompleteData("Cadence anchor follows next billing date")
    if frequency in WEEKS:
        index, remainder = divmod((next_date - anchor).days, 7 * WEEKS[frequency])
    else:
        index, remainder = divmod(
            (next_date.year - anchor.year) * 12 + next_date.month - anchor.month, MONTHS[frequency]
        )
    if remainder or _scheduled(anchor, index, frequency) != next_date:
        raise IncompleteData("Next billing date does not match reviewed cadence anchor")
    finite_end = profile["recurring_end_date"]
    stop = min(end, date.fromisoformat(finite_end)) if finite_end else end
    result = []
    while next_date <= stop:
        result.append(next_date)
        index += 1
        if next_date == stop:
            break
        try:
            next_date = _scheduled(anchor, index, frequency)
        except (OverflowError, ValueError) as exc:
            raise IncompleteData("Recurrence exceeds supported date range") from exc
    return result


def recurring_scenario(
    *,
    start: date,
    end: date,
    timestamp: str,
    currency: str,
    profiles_by_view: dict[str, list[dict[str, Any]]],
    invoices: list[dict[str, Any]],
    reads_complete: bool,
    assumptions: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Return labelled billing events and only explicitly reviewed additional cash.

    Input groups come from complete separate active/inactive/draft view reads. Each
    active profile needs a reviewed anchor, end_inclusive=True, a nonnegative
    payment_delay_days, and per-date overlap evidence: additional_dates or generated
    (billing-date -> existing invoice URL). No undocumented automatic relationship
    matching, FX conversion, or invoice-creation operation is performed.
    """
    from datetime import timedelta

    if end < start or (end - start).days > 3660:
        raise ValueError("Supply an ordered scenario horizon of at most ten years")
    if not currency or datetime.fromisoformat(timestamp.replace("Z", "+00:00")).tzinfo is None:
        raise ValueError("Supply currency and timezone-aware snapshot timestamp")
    if set(profiles_by_view) != {"active", "inactive", "draft"}:
        raise IncompleteData("Collect active, inactive and draft views separately")
    rows = [row for group in profiles_by_view.values() for row in group]
    require_fields(rows, "url", "recurring profile")
    unique(rows)
    invoice_map = {row["url"]: row for row in unique(invoices)}
    missing = [] if reads_complete else ["Profile/invoice reads are incomplete"]
    result: dict[str, Any] = {
        "status": "incomplete",
        "timestamp": timestamp,
        "currency": currency,
        "groups": {view: [row["url"] for row in group] for view, group in profiles_by_view.items()},
        "events": [],
        "commitments": [],
        "missing_inputs": missing,
    }
    for profile in profiles_by_view["active"]:
        source = profile["url"]
        try:
            require_fields(
                [profile],
                "frequency recurring_status next_recurs_on recurring_end_date currency total_value",
                "active profile",
            )
            if profile["recurring_status"] != "Active":
                raise IncompleteData("Active view/status conflict")
            if profile["currency"] != currency:
                raise IncompleteData("Keep currencies separate; select a single-currency profile scope")
            amount = number(profile["total_value"])
            review = assumptions.get(source, {})
            if review.get("end_inclusive") is not True:
                raise IncompleteData("Confirm inclusive-end scenario convention")
            if not review.get("anchor"):
                raise IncompleteData("Review cadence anchor and month-end clamping assumption")
            if date.fromisoformat(profile["next_recurs_on"]) < start:
                raise IncompleteData("Stale next date needs reconciliation before recurrence expansion")
            dates = billing_dates(profile, end=end, anchor=date.fromisoformat(review["anchor"]))
            generated = review.get("generated", {})
            additional = review.get("additional_dates", [])
            delay = review.get("payment_delay_days")
            for dated in dates:
                key = dated.isoformat()
                event = {
                    "source": source,
                    "billing_date": key,
                    "amount": amount,
                    "currency": currency,
                    "status": "incomplete",
                }
                result["events"].append(event)
                if not reads_complete:
                    continue
                if key in generated and key in additional:
                    missing.append(f"{source} {key}: conflicting overlap decisions")
                    continue
                if key in generated:
                    invoice = invoice_map.get(generated[key])
                    if invoice is None or invoice.get("currency") != currency or invoice.get("dated_on") != key:
                        missing.append(f"{source} {key}: generated invoice evidence unavailable or mismatched")
                        continue
                    event.update(status="already_generated", invoice=invoice["url"])
                    continue
                if key not in additional:
                    missing.append(f"{source} {key}: unresolved generated-invoice/balance overlap")
                    continue
                if type(delay) is not int or delay < 0:
                    missing.append(f"{source} {key}: missing reviewed payment-delay assumption")
                    continue
                expected = dated + timedelta(days=delay)
                event.update(status="scenario", expected_receipt_date=expected.isoformat())
                result["commitments"].append(
                    {
                        "url": source + "#scenario-" + key,
                        "parent": source,
                        "date": expected.isoformat(),
                        "billing_date": key,
                        "currency": currency,
                        "amount": str(amount),
                        "additional": True,
                    }
                )
        except (IncompleteData, KeyError, ValueError, TypeError, OverflowError) as exc:
            missing.append(f"{source}: {exc}")
    result["status"] = "incomplete" if missing else "complete"
    return result
