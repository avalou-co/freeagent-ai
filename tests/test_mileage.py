from types import SimpleNamespace

from freeagent_ai import mcp_server
from freeagent_ai.public_tools import REGISTRY, Dispatcher


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
