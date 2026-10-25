"""Offline tool recorder for assistant receipt evaluations; never calls FreeAgent.

Pass one JSON tool call on stdin. Append synthetic requests/results to --transcript.
This is an evaluation adapter, not an approval or accounting policy implementation.
"""

import argparse
import json
from pathlib import Path
from urllib.parse import urlsplit

BASE = "https://api.freeagent.com/v2/"
SCENARIOS = ("clean", "duplicate", "lookup_failure", "ambiguous_write", "failed_readback")


def respond(scenario, tool, arguments):
    """Return canned provider evidence without evaluating the assistant's decision."""
    if tool == "freeagent_get":
        path = arguments["path"]
        endpoint = urlsplit(path).path.strip("/")
        if endpoint.startswith("v2/"):
            endpoint = endpoint[3:]
        if endpoint == "company":
            return {"company": {"url": BASE + "company/1", "name": "Synthetic Review Co", "currency": "GBP"}}
        if endpoint == "users/me":
            return {"user": {"url": BASE + "users/1", "first_name": "Example", "last_name": "Claimant"}}
        if endpoint == "categories":
            return {"categories": [{"url": BASE + "categories/285", "description": "Travel"}]}
        if endpoint == "contacts":
            return {"contacts": [{"url": BASE + "contacts/1", "organisation_name": "Example Supplies"}]}
        if endpoint == "expenses":
            records = []
            if scenario == "duplicate":
                records = [
                    {
                        "url": BASE + "expenses/101",
                        "receipt_reference": "R-TEST-22",
                        "dated_on": "2026-10-02",
                        "currency": "EUR",
                        "gross_value": "-60.00",
                        "description": "Example Travel",
                    }
                ]
            return {"expenses": records}
        if endpoint == "bills":
            if scenario == "lookup_failure":
                return {"error": "Synthetic pagination failure; collection incomplete"}
            return {"bills": []}
        if endpoint == "expenses/101":
            return {
                "expense": {
                    "url": BASE + endpoint,
                    "receipt_reference": "R-TEST-22",
                    "dated_on": "2026-10-02",
                    "currency": "EUR",
                    "gross_value": "-60.00",
                    "description": "Example Travel",
                }
            }
        if endpoint in {"expenses/901", "bills/901"}:
            return {"error": "Synthetic outcome unresolved; inspect account before retry"}
        return {"error": "Read not configured in synthetic stub"}
    if tool in {"create_expense", "create_bill"}:
        kind = tool.removeprefix("create_")
        url = BASE + kind + "s/901"
        if scenario == "ambiguous_write":
            return {"error": "Synthetic POST timeout; outcome unknown; no automatic retry"}
        if scenario == "failed_readback":
            return {"error": "Created " + url + "; synthetic GET timeout; readback unverified"}
        record = {
            key: value
            for key, value in arguments.items()
            if key not in {"receipt_path", "attachment_path", "receipt", "attachment", "confirmed"}
        }
        if "items" in record:
            record["bill_items"] = record.pop("items")
        record.update(url=url, attachment={"file_name": "synthetic-source", "content_type": "application/x-pdf"})
        return {kind: record}
    return {"error": "Unsupported synthetic tool"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--transcript", type=Path, required=True)
    args = parser.parse_args()
    request = json.loads(input())
    response = respond(args.scenario, request["tool"], request["arguments"])
    event = {"scenario": args.scenario, "request": request, "response": response}
    with args.transcript.open("a") as stream:
        stream.write(json.dumps(event, sort_keys=True) + "\n")
    print(json.dumps(response))


if __name__ == "__main__":
    main()
