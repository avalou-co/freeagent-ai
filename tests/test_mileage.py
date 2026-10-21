import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest

from freeagent_ai import mcp_server
from freeagent_ai.public_tools import REGISTRY, Dispatcher

PREVIEW = runpy.run_path(str(Path(__file__).resolve().parents[1] / ".agents/skills/mileage/scripts/preview.py"))[
    "preview"
]


def basis(prior="90"):
    # Synthetic rates and threshold, deliberately not a tax-policy fixture.
    return {
        "prior_miles": prior,
        "threshold": "100",
        "basic_rate": "0.50",
        "additional_rate": "0.20",
        "currency": "GBP",
        "quantum": "0.01",
        "from": "2026-01-01",
        "to": "2026-12-31",
    }


def journey(identifier="a", **changes):
    return {
        "id": identifier,
        "group": "claimant-period-car-pool",
        "date": "2026-05-01",
        "purpose": "Site visit",
        "vehicle": "car-a",
        "distance": "20",
        "unit": "miles",
        **changes,
    }


def test_kilometres_cross_band_and_shared_car_pool():
    result = PREVIEW(
        {
            "groups": {"claimant-period-car-pool": basis()},
            "journeys": [
                journey(distance="32.18688", unit="km"),
                journey("b", vehicle="car-b", date="2026-05-02", distance="5"),
            ],
        }
    )
    assert result[0]["miles"] == "20"
    assert result[0]["basic_miles"] == "10"
    assert result[0]["additional_miles"] == "10"
    assert result[0]["estimated_amount"] == "7.00"
    assert result[1]["prior_miles"] == "110"
    assert result[1]["estimated_amount"] == "1.00"


def test_chronology_duplicate_flags_and_separate_pool():
    result = PREVIEW(
        {
            "groups": {"claimant-period-car-pool": basis(), "other": basis("0")},
            "journeys": [
                journey("later", date="2026-05-03"),
                journey(),
                journey("duplicate"),
                journey("bike", group="other", vehicle="bike"),
            ],
        }
    )
    assert result[0]["id"] == "a"
    assert result[1]["possible_duplicates"] == ["a"]
    assert result[2]["prior_miles"] == "0"
    assert result[2]["estimated_amount"] == "10.00"


@pytest.mark.parametrize("prior,expected", [("100", "4.00"), ("0", "10.00"), ("99.5", "4.15")])
def test_threshold_boundaries(prior, expected):
    assert (
        PREVIEW({"groups": {"claimant-period-car-pool": basis(prior)}, "journeys": [journey()]})[0]["estimated_amount"]
        == expected
    )


@pytest.mark.parametrize(
    "change", [{"prior_miles": None}, {"prior_miles": "NaN"}, {"basic_rate": "-1"}, {"quantum": "0.05"}]
)
def test_missing_or_invalid_basis_cannot_produce_amount(change):
    with pytest.raises((ValueError, TypeError)):
        PREVIEW({"groups": {"claimant-period-car-pool": {**basis(), **change}}, "journeys": [journey()]})


@pytest.mark.parametrize(
    "change", [{"unit": "yards"}, {"distance": "0"}, {"distance": 20.1}, {"date": "2027-01-01"}, {"date": "20260501"}]
)
def test_invalid_or_out_of_period_journey_cannot_produce_amount(change):
    with pytest.raises(ValueError):
        PREVIEW({"groups": {"claimant-period-car-pool": basis()}, "journeys": [journey(**change)]})


def test_mileage_payload_and_readback_preserve_provider_result(monkeypatch):
    calls = []
    actual = {"expense": {"url": mcp_server.BASE + "expenses/12", "gross_value": "-7.01", "mileage": "20"}}

    def call(method, path, body=None):
        calls.append((method, path, body))
        return actual

    monkeypatch.setattr(mcp_server, "call", call)
    result = mcp_server.create_mileage_expense(
        "u", "2026-05-01", "Site visit", "20", "Car", 1, engine_type="Diesel", engine_size="All", have_vat_receipt=False
    )
    assert result == actual
    assert calls[0][2] == {
        "expense": {
            "user": "u",
            "category": "Mileage",
            "dated_on": "2026-05-01",
            "description": "Site visit",
            "mileage": "20",
            "vehicle_type": "Car",
            "reclaim_mileage": 1,
            "engine_type": "Diesel",
            "engine_size": "All",
            "have_vat_receipt": False,
        }
    }
    assert calls[1][:2] == ("GET", "expenses/12")


def test_rebill_only_flag_is_not_overwritten(monkeypatch):
    payloads = []
    monkeypatch.setattr(
        mcp_server,
        "call",
        lambda method, path, body=None: payloads.append(body) or {"expense": {"url": mcp_server.BASE + "expenses/12"}},
    )
    mcp_server.create_mileage_expense("u", "2026-05-01", "Visit", "2", "Bicycle", 0)
    assert payloads[0]["expense"]["reclaim_mileage"] == 0
    assert "engine_type" not in payloads[0]["expense"]


def test_hosted_mileage_settings_fixed_read_and_projection():
    calls = []
    settings = {
        "mileage_rates": [{"from": "2026-01-01", "to": "2026-12-31", "value": {"Car": {"basic_rate": "0.50"}}}],
        "engine_type_and_size_options": [],
    }

    def call(method, path, body, **kwargs):
        calls.append((method, path))
        return {"mileage_settings": {**settings, "debug": "private"}}

    result = Dispatcher(None, "", "")._run(
        REGISTRY["get_mileage_settings"], {}, SimpleNamespace(call=call, base=mcp_server.BASE)
    )
    assert result == {"mileage_settings": settings}
    assert calls == [("GET", "expenses/mileage_settings")]
