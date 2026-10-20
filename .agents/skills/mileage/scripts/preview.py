"""Decimal preview arithmetic for an explicitly chosen allowance basis. No API calls."""

import json
import sys
from datetime import date
from decimal import ROUND_HALF_UP, Decimal


def number(value):
    if not isinstance(value, str):
        raise ValueError("Use decimal strings, not binary floating-point numbers")
    result = Decimal(value)
    if not result.is_finite() or result < 0:
        raise ValueError("Expected a finite nonnegative decimal")
    return result


def preview(data):
    """Groups supply prior_miles, threshold, rates, period bounds, currency and quantum.

    Group keys identify the claimant/period/allowance pool established by the agent.
    Journey rows supply id, group, date, purpose, vehicle, distance and unit.
    Rates are currency units per mile; this helper never chooses an allowance policy.
    """
    groups = data["groups"]
    counters = {key: number(group["prior_miles"]) for key, group in groups.items()}
    results, seen, identifiers = [], {}, set()
    for row in sorted(data["journeys"], key=lambda row: date.fromisoformat(row["date"])):
        if row["id"] in identifiers:
            raise ValueError("Journey IDs must be unique")
        identifiers.add(row["id"])
        group = groups[row["group"]]
        dated_on = date.fromisoformat(row["date"])
        if row["date"] != dated_on.isoformat():
            raise ValueError("Journey dates must use YYYY-MM-DD")
        if not date.fromisoformat(group["from"]) <= dated_on <= date.fromisoformat(group["to"]):
            raise ValueError("Journey is outside the supplied basis interval")
        distance = number(row["distance"])
        if not distance or row["unit"] not in {"miles", "km"}:
            raise ValueError("Provide positive distance and unit miles or km")
        miles = distance / Decimal("1.609344") if row["unit"] == "km" else distance
        prior = counters[row["group"]]
        basic = min(miles, max(Decimal(0), number(group["threshold"]) - prior))
        additional = miles - basic
        quantum = number(group["quantum"])
        if not quantum or quantum != Decimal(1).scaleb(quantum.as_tuple().exponent):
            raise ValueError("Currency quantum must be a power of ten, e.g. 0.01")
        amount = (basic * number(group["basic_rate"]) + additional * number(group["additional_rate"])).quantize(
            quantum, rounding=ROUND_HALF_UP
        )
        signature = (row["group"], row["date"], row["vehicle"], miles, row["purpose"].strip().casefold())
        duplicates = list(seen.get(signature, []))
        seen.setdefault(signature, []).append(row["id"])
        counters[row["group"]] = prior + miles
        results.append(
            {
                **row,
                "miles": format(miles, "f"),
                "prior_miles": format(prior, "f"),
                "basic_miles": format(basic, "f"),
                "additional_miles": format(additional, "f"),
                "after_miles": format(prior + miles, "f"),
                "estimated_amount": format(amount, "f"),
                "currency": group["currency"],
                "possible_duplicates": duplicates,
            }
        )
    return results


if __name__ == "__main__":
    print(json.dumps(preview(json.load(sys.stdin)), indent=2))
